"""无窗口授权：从已确认的聊天输入或主动选择的剪贴板取得 Key，DPAPI 加密保存。

不扫描浏览器，不输出 Key，不把明文写入配置/命令行。不使用机器级保护范围。
"""
import base64
import ctypes
import json
import os
from pathlib import Path
import tempfile
import time
import updates
import weread_notes as core


class AuthError(core.ExportError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def protect(data: bytes, decrypt=False) -> bytes:
    if os.name != 'nt':
        raise AuthError('secure_storage_unavailable', '当前系统尚未接入安全凭证存储，可使用 WEREAD_API_KEY 环境变量。')

    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    crypto = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    function = crypto.CryptUnprotectData if decrypt else crypto.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
    function.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    # UI_FORBIDDEN=1；没有 LOCAL_MACHINE=4，因此绑定当前用户而非任意本机用户。
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise AuthError('secure_storage_unavailable', 'Windows 凭证保护不可用或当前执行用户与授权时不同，请在相同执行环境重新授权。')
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(ctypes.cast(outgoing.data, ctypes.c_void_p))


def vault_path():
    return updates.state_root() / 'credential.dpapi.json'


def save_key(key, remember=False):
    core.validate_api_key(key)
    encrypted = protect(key.encode('utf-8'))
    value = {'schema': 1, 'protection': 'windows-dpapi-current-user',
             'expires_at': None if remember else time.time() + 1800,
             'ciphertext': base64.b64encode(encrypted).decode('ascii')}
    path = vault_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # 独占临时文件，写完才原子替换，绝不写明文；失败不破坏旧授权。
    descriptor, filename = tempfile.mkstemp(prefix='credential-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream)
        os.replace(filename, path)
    finally:
        Path(filename).unlink(missing_ok=True)


def get_key():
    key = os.environ.get('WEREAD_API_KEY', '')
    if key:
        core.validate_api_key(key)
        return key
    path = vault_path()
    if not path.exists():
        raise AuthError('auth_required', '请在 Codex 的独立授权步骤发送官方 Key，再回复“确定”；验证成功后才继续选书和导出。')
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('schema') != 1 or value.get('protection') != 'windows-dpapi-current-user':
            raise ValueError()
        expires = value.get('expires_at')
        if expires is not None and (not isinstance(expires, (int, float)) or time.time() >= expires):
            raise AuthError('auth_expired', '临时授权已过期，请在对话中重新发送 Key 并确认授权。')
        key = protect(base64.b64decode(value['ciphertext'], validate=True), decrypt=True).decode('utf-8')
        core.validate_api_key(key)
        return key
    except AuthError:
        raise
    except Exception:
        raise AuthError('auth_invalid', '本地授权记录无法读取，请重新授权。') from None


def status():
    try:
        get_key()
        return {'available': True, 'source': 'environment' if os.environ.get('WEREAD_API_KEY') else 'encrypted_local',
                'server_validated': False}
    except core.ExportError as exc:
        return {'available': False, 'code': getattr(exc, 'code', 'auth_invalid'), 'server_validated': False}


def forget():
    vault_path().unlink(missing_ok=True)
    return {'forgotten': True, 'environment_key_present': bool(os.environ.get('WEREAD_API_KEY'))}
