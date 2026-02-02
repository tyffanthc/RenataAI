[Setup]
AppName=RenataAI Voice Pack (Piper PL)
AppVersion=0.9.0-pl1
DefaultDirName={userappdata}\RenataAI\voice\piper
DefaultGroupName=RenataAI Voice Pack
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputBaseFilename=Renata-VoicePack-Piper-PL-Installer-0.9.0-pl1
Compression=lzma
SolidCompression=yes
SetupIconFile=
UninstallDisplayIcon=

[Files]
Source: "payload\piper.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "payload\models\pl_PL-gosia-medium.onnx"; DestDir: "{app}\models"; Flags: ignoreversion
Source: "payload\models\pl_PL-gosia-medium.json"; DestDir: "{app}\models"; Flags: ignoreversion
Source: "payload\voicepack.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "payload\VOICEPACK_LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
