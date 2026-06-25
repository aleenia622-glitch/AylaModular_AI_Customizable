import ctypes
from pathlib import Path

# Try to import comtypes for modern IDesktopWallpaper COM interface
try:
    import comtypes
    from comtypes import IUnknown, GUID, COMMETHOD
    from ctypes import HRESULT
    from ctypes.wintypes import LPCWSTR

    class IDesktopWallpaper(IUnknown):
        _iid_ = GUID('{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'SetWallpaper',
                      (['in'], LPCWSTR, 'monitorID'),
                      (['in'], LPCWSTR, 'wallpaper')),
        ]
    HAS_COMTYPES = True
except ImportError:
    HAS_COMTYPES = False

def mudar_papel_parede(caminho_imagem: str) -> str:
    try:
        p = Path(caminho_imagem).expanduser().resolve()
        if not p.is_file(): return f"Arquivo não encontrado: {p}"
        
        # 1. Update Registry for persistence across reboots and cache consistency
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "Wallpaper", 0, winreg.REG_SZ, str(p))
            winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, "10") # 10 = Fill
            winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "0")
            winreg.CloseKey(key)
        except Exception:
            pass

        # 2. Try the modern IDesktopWallpaper COM interface first (solves Windows 11 slideshow/spotlight caching issues)
        if HAS_COMTYPES:
            try:
                comtypes.CoInitialize()
                CLSID_DesktopWallpaper = GUID('{C2CF3110-460E-4fc1-B9D0-8A1C0C9CC4BD}')
                wallpaper_instance = comtypes.CoCreateInstance(
                    CLSID_DesktopWallpaper, 
                    interface=IDesktopWallpaper
                )
                wallpaper_instance.SetWallpaper(None, str(p))
                return f"🖼️ Papel de parede alterado com sucesso!"
            except Exception:
                pass
            finally:
                comtypes.CoUninitialize()

        # 3. Fallback to ctypes SystemParametersInfoW
        result = ctypes.windll.user32.SystemParametersInfoW(20, 0, str(p), 3)
        if result:
            return f"🖼️ Papel de parede alterado!"
        else:
            return f"Erro: Falha ao aplicar o papel de parede via SystemParametersInfo."
            
    except Exception as e:
        return f"Erro: {e}"

TOOL_MAP["mudar_papel_parede"] = mudar_papel_parede
FUNCTION_DECLARATIONS.append({"name": "mudar_papel_parede", "description": "Muda o papel de parede do Windows.", "parameters": {"type": "object", "properties": {"caminho_imagem": {"type": "string"}}, "required": ["caminho_imagem"]}})

