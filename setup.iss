[Setup]
AppName=MotionKeyboardMapper
AppVersion=1.03
AppPublisher=dissdannm
DefaultDirName={pf}\MotionKeyboardMapper
DefaultGroupName=MotionKeyboardMapper
OutputDir=dist_installer
OutputBaseFilename=MotionKeyboardMapper_v1.03_Setup
Compression=lzma
SolidCompression=yes
UninstallDisplayName=MotionKeyboardMapper v1.03
SetupIconFile=assets\icon.ico

[Files]
Source: "dist\MotionKeyboardMapper.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MotionKeyboardMapper"; Filename: "{app}\MotionKeyboardMapper.exe"
Name: "{commondesktop}\MotionKeyboardMapper"; Filename: "{app}\MotionKeyboardMapper.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面图标"; GroupDescription: "附加任务:"

[Run]
Filename: "{app}\MotionKeyboardMapper.exe"; Description: "启动 MotionKeyboardMapper"; Flags: nowait postinstall skipifsilent
