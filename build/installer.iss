; Inno Setup 6（免费，GitHub 的 Windows 机器上自带）把 dist\pkg 打成 一个安装程序.exe。PLAN v1.4 第 4 步。
; 编译：iscc /DAppVer=1.0.0 build\installer.iss
#ifndef AppVer
  #define AppVer "0.0.0"
#endif
[Setup]
AppId={{6B0D7C55-2B9E-4C2E-9A61-3C1E1A7F4B21}
AppName=WhatsApp客户提取
AppVersion={#AppVer}
AppPublisher=Jalane
; 安装路径只用英文：中文路径在部分 Python / Node 工具里会出错
DefaultDirName={autopf}\WhatsAppLeadTool
DefaultGroupName=WhatsApp客户提取
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=WhatsApp客户提取-安装程序-{#AppVer}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
WizardStyle=modern
; 只给当前用户装：不用管理员权限，也不会弹 UAC
PrivilegesRequired=lowest
UninstallDisplayName=WhatsApp客户提取

[Files]
Source: "..\dist\pkg\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; pythonw.exe：不弹黑色命令行窗口
Name: "{autodesktop}\WhatsApp客户提取"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"
Name: "{group}\WhatsApp客户提取"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"
Name: "{group}\打开表格文件夹"; Filename: "{userdocs}\WhatsApp客户提取\表格"

[Dirs]
Name: "{userdocs}\WhatsApp客户提取\表格"

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"; Description: "现在打开"; Flags: nowait postinstall skipifsilent

; 卸载只删程序；文档\WhatsApp客户提取\表格 和 %LOCALAPPDATA% 里的数据、登录信息都保留（重装后接着用）
