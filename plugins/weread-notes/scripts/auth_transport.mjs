/** 宿主 JS 后台工具可调用：Key 只经 stdin 交给 Python，不能拼接进 shell/argv。
 * 聊天输入本身会留在会话历史；这里不会额外打印 Key 或保存明文临时文件。
 */
import { spawn } from 'node:child_process';

export async function authorizeFromChat({ python, launcher, key, confirmed = false, remember = false }) {
  if (!confirmed) return { status: 'confirmation_required', code: 'confirmation_required' };
  if (typeof key !== 'string' || !key.startsWith('wrk-') || key.length <= 4 || key.length > 8192 || /\s/.test(key)) {
    return { error: 'Key 格式不正确，请只发送官方 wrk- Key。' };
  }
  const args = [launcher, 'auth', 'import', '--stdin', '--confirmed'];
  if (remember) args.push('--remember');
  return await new Promise(resolve => {
    const child = spawn(python, args, { shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    let output = '', settled = false;
    const finish = value => { if (!settled) { settled = true; resolve(value); } };
    child.on('error', () => finish({ error: '后台授权进程无法启动。' }));
    child.stdin.on('error', () => finish({ error: '后台授权输入管道已关闭。' }));
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', value => {
      output += value;
      if (output.length > 200000) {
        child.kill();
        finish({ error: '授权响应超过限制。' });
      }
    });
    // 不回显原始 stderr；第三方库意外输出凭证时也不会传回聊天。
    child.stderr.resume();
    child.on('close', () => {
      try {
        const value = JSON.parse(output);
        // 只向调用者返回授权摘要，不转发任意原始内容。
        finish({ authorized: value.authorized === true, remembered: value.remembered === true,
                 status: value.status, code: value.code,
                 expires_in_seconds: value.expires_in_seconds,
                 failed: value.authorized !== true });
      } catch {
        finish({ error: '授权未完成，请检查后台运行环境。' });
      }
    });
    child.stdin.end(key + '\n', 'utf8');
  });
}
