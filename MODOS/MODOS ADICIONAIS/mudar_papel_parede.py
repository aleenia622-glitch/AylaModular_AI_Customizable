import sys
import os
from pathlib import Path

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))
import ayla_state
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

def mudar_papel_parede(caminho_imagem: str = None) -> str:
    try:
        p = None
        anexo = ayla_state.ULTIMO_ANEXO_IMAGEM.get()
        
        if anexo:
            try:
                img_bytes, mime_type = anexo
                
                # Pasta de saída da Ayla
                pasta_saida = base_dir / "Aylafotitos"
                pasta_saida.mkdir(parents=True, exist_ok=True)
                
                import uuid
                from datetime import datetime as _dt
                
                ext = ".png"
                if mime_type:
                    mime_lower = mime_type.lower()
                    if "jpeg" in mime_lower or "jpg" in mime_lower:
                        ext = ".jpg"
                    elif "webp" in mime_lower:
                        ext = ".webp"
                    elif "bmp" in mime_lower:
                        ext = ".bmp"
                
                data_hora = _dt.now().strftime("%Y%m%d_%H%M%S")
                nome_arquivo = f"wallpaper_{data_hora}_{uuid.uuid4().hex[:6]}{ext}"
                caminho_final = pasta_saida / nome_arquivo
                
                with open(caminho_final, "wb") as f:
                    f.write(img_bytes)
                
                p = caminho_final
            except Exception as e:
                return f"Erro ao processar anexo de imagem: {e}"
        elif caminho_imagem:
            p = Path(caminho_imagem).expanduser().resolve()
            
        if not p or not p.is_file():
            if caminho_imagem:
                return f"Arquivo não encontrado: {caminho_imagem}"
            return "⚠️ Nenhum arquivo de imagem foi fornecido e não há imagem anexada!"
        
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
FUNCTION_DECLARATIONS.append({
    "name": "mudar_papel_parede",
    "description": "Muda o papel de parede do Windows. Se houver uma imagem anexada no chat, ela será definida automaticamente.",
    "parameters": {
        "type": "object",
        "properties": {
            "caminho_imagem": {
                "type": "string",
                "description": "Caminho local da imagem para usar como papel de parede. Opcional se houver uma imagem anexada na mensagem."
            }
        }
    }
})

