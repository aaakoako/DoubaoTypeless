Unicode True
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "StrFunc.nsh"
${StrStr}
!ifndef VERSION
  !error "VERSION is required"
!endif
!ifndef PAYLOAD
  !error "PAYLOAD is required"
!endif
!ifndef OUTPUT
  !error "OUTPUT is required"
!endif
!ifdef TEST_INSTALL
  !define PRODUCT "DoubaoTypeless Installer Test"
  !define REGKEY "Software\DoubaoTypelessInstallerTest"
!else
  !define PRODUCT "DoubaoTypeless"
  !define REGKEY "Software\DoubaoTypeless"
!endif
Name "${PRODUCT} ${VERSION}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\${PRODUCT}"
InstallDirRegKey HKCU "${REGKEY}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${PRODUCT}"
VIAddVersionKey "FileDescription" "${PRODUCT} Installer"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "DoubaoTypeless contributors"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TEXT "安装完成。请关闭正在运行的旧版本，再从开始菜单打开 DoubaoTypeless。设置、草稿和图片保存在应用目录之外，升级和卸载不会删除它们。"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Section "Application"
  SetShellVarContext current
  IfFileExists "$INSTDIR\*.*" 0 owned
  IfFileExists "$INSTDIR\.typeless-install" owned
  MessageBox MB_OK|MB_ICONSTOP "该文件夹已有其他文件，请选择空文件夹。" /SD IDOK
  Abort
  owned:
  ClearErrors
  CreateDirectory "$INSTDIR"
  IfErrors install_failed
  FileOpen $0 "$INSTDIR\.typeless-install" w
  IfErrors install_failed
  FileWrite $0 "DoubaoTypeless installation"
  FileClose $0
  IfErrors install_failed
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  IfErrors install_failed
  SetOutPath "$INSTDIR\versions\${VERSION}"
  IfErrors install_failed
  File /r "${PAYLOAD}\*.*"
  IfErrors install_failed
  WriteRegStr HKCU "${REGKEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT}" "DisplayName" "${PRODUCT}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT}" "DisplayIcon" "$INSTDIR\versions\${VERSION}\DoubaoTypeless.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT}" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT}" "NoRepair" 1
!ifndef TEST_INSTALL
  IfErrors install_failed
  CreateShortcut "$SMPROGRAMS\DoubaoTypeless.lnk" "$INSTDIR\versions\${VERSION}\DoubaoTypeless.exe"
  IfErrors install_failed
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "DoubaoTypelessV3"
  ClearErrors
  ${If} $0 != ""
    ${StrStr} $1 $0 " --minimized"
    ${If} $1 != ""
      WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "DoubaoTypelessV3" '$\"$INSTDIR\versions\${VERSION}\DoubaoTypeless.exe$\"$1'
    ${EndIf}
  ${EndIf}
!endif
  IfErrors install_failed
  Goto install_done
  install_failed:
  MessageBox MB_OK|MB_ICONSTOP "安装未完成，请检查磁盘空间和目录权限后重试。用户数据未删除。" /SD IDOK
  SetErrorLevel 2
  Abort
  install_done:
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  IfFileExists "$INSTDIR\.typeless-install" 0 refuse
  ReadRegStr $9 HKCU "${REGKEY}" "InstallDir"
  ClearErrors
  RMDir /r "$INSTDIR\versions"
  IfErrors locked
  Delete "$INSTDIR\.typeless-install"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  ${If} $9 == "$INSTDIR"
    DeleteRegKey HKCU "${REGKEY}"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT}"
!ifndef TEST_INSTALL
    Delete "$SMPROGRAMS\DoubaoTypeless.lnk"
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "DoubaoTypelessV3"
!endif
  ${EndIf}
  Goto done
  locked:
  MessageBox MB_OK|MB_ICONSTOP "部分程序文件仍在使用。请退出 DoubaoTypeless 后重新卸载。卸载入口和用户数据已保留。" /SD IDOK
  SetErrorLevel 2
  Abort
  refuse:
  MessageBox MB_OK|MB_ICONSTOP "安装标记缺失，未删除任何文件。" /SD IDOK
  SetErrorLevel 2
  Abort
  done:
SectionEnd
