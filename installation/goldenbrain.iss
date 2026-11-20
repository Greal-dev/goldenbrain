; GoldenBrain — installateur Windows (Inno Setup 6), compilé par scripts/construire_windows.py.
; Installation par utilisateur, sans droits administrateur : Python portable, Git portable (MinGit),
; graine de l'application, raccourci du menu Démarrer ; lancement proposé à la fin.
; La copie de travail (%LOCALAPPDATA%\GoldenBrain\app : réglages, état, mises à jour) n'appartient
; pas à l'installateur : la désinstallation la laisse en place (INV-PAQUET-1).
; Les dossiers python, git et graine sont préparés par le script de construction dans {#Source}.

#ifndef Source
  #error "Source non défini : utiliser scripts/construire_windows.py"
#endif
#ifndef Version
  #define Version "1"
#endif

[Setup]
AppId=GoldenBrain
AppName=GoldenBrain
AppVersion={#Version}
AppPublisher=GoldenBrain
DefaultDirName={localappdata}\Programs\GoldenBrain
DefaultGroupName=GoldenBrain
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=GoldenBrain-installation
SetupIconFile={#Source}\GoldenBrain.ico
UninstallDisplayIcon={app}\GoldenBrain.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
fr.Lancer=Lancer GoldenBrain
en.Lancer=Start GoldenBrain
de.Lancer=GoldenBrain starten
es.Lancer=Iniciar GoldenBrain

[Files]
Source: "{#Source}\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Source}\git\*"; DestDir: "{app}\git"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Source}\graine\*"; DestDir: "{app}\graine"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Source}\GoldenBrain.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Source}\deja_lance.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Source}\langue.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Source}\GoldenBrain.ico"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Une graine plus ancienne ne doit pas laisser de fichiers orphelins dans la nouvelle.
Type: filesandordirs; Name: "{app}\graine"

[Icons]
Name: "{group}\GoldenBrain"; Filename: "{app}\GoldenBrain.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\GoldenBrain.ico"; Flags: runminimized

[Run]
Filename: "{app}\GoldenBrain.cmd"; WorkingDir: "{app}"; Description: "{cm:Lancer}"; Flags: postinstall nowait skipifsilent runminimized shellexec
