; 🤖 UNI_Setup.iss — Inno Setup (ФАЗА 7, F-02: UNI-Setup.exe)
; Сборка на целевой Windows-машине с установленным Inno Setup (iscc):
;     iscc UNI_Setup.iss
; Результат: UNI-Setup.exe (инсталлятор). Устанавливает dist/ целиком.
;
; F-02 требования: ярлык, опц. автозапуск, модель при первом запуске с прогрессом,
; VC++/WebView2, /VERYSILENT. Пруф (чистая VM без Python/Node/LM Studio) — вне
; этого окружения (DECISION, см. REPORT_PACKAGING.md).

#define MyAppName "UNI"
#define MyAppVersion "1.0.0"
#define MyPublisher "UNI Project"
#define MyURL "https://github.com/DieWillz/UNI-test"
; Каталог сборки (рядом с UNI.exe, electron/, runtime/llama/)
#define SrcDir "dist"

[Setup]
AppId={{8F3C5A1E-2B7D-4C9A-9E11-7C6D5F4B3A21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
AppPublisherURL={#MyURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename=UNI-Setup
SetupIconFile={#SrcDir}\uni.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; VC++ redist + WebView2 — через отдельные run-секции (проверка наличия)
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
; Весь dist/ целиком (UNI.exe + electron/ + runtime/llama/ + config.example.yaml)
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\UNI.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\UNI.exe"; WorkingDir: "{app}"
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\UNI.exe"; Tasks: autostart

[Tasks]
Name: "autostart"; Description: "Запускать UNI при старте Windows"; GroupDescription: "Параметры запуска:"

[Run]
; VC++ redist (если не установлен) — скачивается при установке
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/quiet /norestart"; StatusMsg: "Установка Visual C++ Redistributable..."; Flags: skipifdoesntexist; Check: VCNotInstalled
; WebView2 runtime (для Electron-оверлея) — скачивается при установке
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Установка WebView2 Runtime..."; Flags: skipifdoesntexist; Check: WebView2NotInstalled
; Первый запуск — поднимает загрузку модели с прогрессом (через UNI.exe --first-run)
Filename: "{app}\UNI.exe"; Parameters: "--first-run"; Description: "Первый запуск UNI (загрузка модели)"; Flags: postinstall nowait runascurrentuser

[Code]
function VCNotInstalled(): Boolean;
begin
  Result := not RegKeyExists(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64');
end;

function WebView2NotInstalled(): Boolean;
var
  Ver: string;
begin
  Result := not RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A08C11}', 'pv', Ver);
end;
