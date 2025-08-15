# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

# Get the base directory - use current working directory instead of __file__
base_dir = Path(os.getcwd())

def find_pygame_binaries():
    """Find pygame DLLs automatically - works in any environment."""
    binaries = []
    try:
        import pygame
        pygame_dir = Path(pygame.__file__).parent
        
        # SDL2 DLL names that pygame needs
        required_dlls = [
            'SDL2.dll',
            'SDL2_image.dll', 
            'SDL2_mixer.dll',
            'SDL2_ttf.dll'
        ]
        
        # Find all DLLs in pygame directory
        for dll_file in pygame_dir.glob('*.dll'):
            binaries.append((str(dll_file), '.'))
            print(f"Including pygame DLL: {dll_file.name}")
            
        print(f"Found {len(binaries)} pygame DLLs")
        return binaries
        
    except ImportError:
        print("Warning: pygame not found, no DLLs will be included")
        return []

# Get pygame DLLs automatically
pygame_binaries = find_pygame_binaries()

a = Analysis(
    ['lemonade_arcade/main.py'],
    pathex=[str(base_dir)],
    binaries=pygame_binaries,
    datas=[
        # Include static files and templates
        ('lemonade_arcade/static', 'lemonade_arcade/static'),
        ('lemonade_arcade/templates', 'lemonade_arcade/templates'),
    ],
    hiddenimports=[
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'fastapi',
        'fastapi.routing',
        'fastapi.staticfiles',
        'fastapi.templating',
        'jinja2',
        'pygame',
        'pygame._sdl2',
        'pygame._sdl2.audio',
        'pygame._sdl2.controller',
        'pygame._sdl2.mixer',
        'pygame._sdl2.sdl2',
        'pygame._sdl2.touch',
        'pygame._sdl2.video',
        'httpx',
        'httpx._client',
        'httpx._config',
        'httpx._models',
        'httpx._types',
        'httpx._auth',
        'httpx._exceptions',
        'httpcore',
        'httpcore._sync',
        'httpcore._async',
        'h11',
        'h2',
        'certifi',
        'charset_normalizer',
        'idna',
        'sniffio',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hook_pygame.py'],
    excludes=['SDL3'],  # Explicitly exclude SDL3 to avoid conflicts
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LemonadeArcade',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Show console window for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='img/icon.ico'
)
