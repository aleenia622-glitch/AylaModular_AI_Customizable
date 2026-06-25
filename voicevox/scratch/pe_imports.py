import struct
from pathlib import Path

def get_dll_imports(dll_path):
    dll_path = Path(dll_path)
    if not dll_path.exists():
        return f"File not found: {dll_path}"
    
    data = dll_path.read_bytes()
    
    # DOS Header
    if data[:2] != b'MZ':
        return "Not a valid PE file (no MZ signature)"
    
    pe_offset = struct.unpack('<I', data[0x3c:0x40])[0]
    if data[pe_offset:pe_offset+4] != b'PE\0\0':
        return "Not a valid PE file (no PE signature)"
    
    # COFF File Header
    coff_header = data[pe_offset+4 : pe_offset+24]
    machine, num_sections, _, _, _, size_opt_header, characteristics = struct.unpack('<HHIIIHH', coff_header)
    
    # Optional Header
    opt_header_offset = pe_offset + 24
    magic = struct.unpack('<H', data[opt_header_offset:opt_header_offset+2])[0]
    
    if magic == 0x20b: # PE32+ (64-bit)
        import_dir_offset = opt_header_offset + 120 # 112 + 8
    elif magic == 0x10b: # PE32 (32-bit)
        import_dir_offset = opt_header_offset + 104 # 96 + 8
    else:
        return f"Unknown PE magic: {magic:#x}"
    
    import_rva, import_size = struct.unpack('<II', data[import_dir_offset:import_dir_offset+8])
    if import_rva == 0 or import_size == 0:
        return "No imports found"
        
    # Section Headers
    section_headers_offset = opt_header_offset + size_opt_header
    sections = []
    for i in range(num_sections):
        offset = section_headers_offset + i * 40
        sec_data = data[offset : offset + 40]
        name = sec_data[:8].rstrip(b'\0').decode('ascii', errors='ignore')
        vsize, vaddr, raw_size, raw_ptr = struct.unpack('<IIII', sec_data[8:24])
        sections.append((name, vaddr, vsize, raw_ptr, raw_size))
        
    def rva_to_offset(rva):
        for name, vaddr, vsize, raw_ptr, raw_size in sections:
            if vaddr <= rva < vaddr + vsize:
                return rva - vaddr + raw_ptr
        return None
        
    import_offset = rva_to_offset(import_rva)
    if import_offset is None:
        return "Could not map import directory RVA to file offset"
        
    imported_dlls = []
    curr_offset = import_offset
    while True:
        descriptor = data[curr_offset : curr_offset + 20]
        if len(descriptor) < 20 or descriptor == b'\0'*20:
            break
            
        _, _, _, name_rva, _ = struct.unpack('<IIIII', descriptor)
        name_offset = rva_to_offset(name_rva)
        if name_offset is not None:
            # Read null-terminated string
            end = data.find(b'\0', name_offset)
            dll_name = data[name_offset:end].decode('ascii', errors='ignore')
            imported_dlls.append(dll_name)
            
        curr_offset += 20
        
    return imported_dlls

# Print imports of msvcp140.dll
dll_path = r"C:\Users\Aleenia\AppData\Local\Programs\Python\Python314\Lib\site-packages\voicevox_core\msvcp140.dll"
print("Imports of msvcp140.dll:")
imports = get_dll_imports(dll_path)
if isinstance(imports, list):
    for imp in imports:
        print(f"  {imp}")
else:
    print(f"Error: {imports}")
