# Le o GetConsoleMode(CONIN$) de outro processo e escreve num arquivo. So leitura, nada e alterado.
# Vive num processo separado de proposito: AttachConsole exige FreeConsole antes, e isso destroi os
# handles de saida de quem chama -- foi o que quebrou a sonda quando isto era uma funcao dela.
param(
    [Parameter(Mandatory)][int]$Alvo,
    [Parameter(Mandatory)][string]$Saida,
    [uint32]$Definir = 0
)

Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class ModoConsole {
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool AttachConsole(uint pid);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool FreeConsole();
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
  static extern IntPtr CreateFileW(string n, uint acc, uint share, IntPtr sa, uint disp, uint fl, IntPtr t);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetConsoleMode(IntPtr h, out uint m);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetConsoleMode(IntPtr h, uint m);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr h);

  // O setRawMode do Node nao liga VIRTUAL_TERMINAL_INPUT; o Claude Code liga. Fixar o modo no valor
  // medido na sessao real e o que torna o alvo um proxy fiel em vez de um parecido.
  public static string Definir(uint pid, uint modo) {
    FreeConsole();
    if (!AttachConsole(pid)) return "(sem console: erro " + Marshal.GetLastWin32Error() + ")";
    IntPtr h = CreateFileW("CONIN$", 0x80000000 | 0x40000000, 3, IntPtr.Zero, 3, 0, IntPtr.Zero);
    if (h == (IntPtr)(-1)) { FreeConsole(); return "(CONIN$ falhou)"; }
    bool ok = SetConsoleMode(h, modo);
    int err = Marshal.GetLastWin32Error();
    CloseHandle(h); FreeConsole();
    return ok ? "definido" : "(SetConsoleMode falhou: " + err + ")";
  }

  public static string Ler(uint pid) {
    FreeConsole();
    if (!AttachConsole(pid)) return "(sem console: erro " + Marshal.GetLastWin32Error() + ")";
    IntPtr h = CreateFileW("CONIN$", 0x80000000 | 0x40000000, 3, IntPtr.Zero, 3, 0, IntPtr.Zero);
    if (h == (IntPtr)(-1)) { FreeConsole(); return "(CONIN$ falhou: " + Marshal.GetLastWin32Error() + ")"; }
    uint m; bool ok = GetConsoleMode(h, out m);
    CloseHandle(h); FreeConsole();
    if (!ok) return "(GetConsoleMode falhou)";
    var s = new StringBuilder("0x" + m.ToString("X4"));
    s.Append((m & 0x0001) != 0 ? " PROCESSED" : " -processed");
    s.Append((m & 0x0002) != 0 ? " LINE" : " -line");
    s.Append((m & 0x0004) != 0 ? " ECHO" : " -echo");
    s.Append((m & 0x0040) != 0 ? " QUICKEDIT" : " -quickedit");
    s.Append((m & 0x0200) != 0 ? " VT_INPUT" : " -vt_input");
    return s.ToString();
  }
}
'@

if ($Definir -ne 0) {
    $r = [ModoConsole]::Definir([uint32]$Alvo, $Definir)
    if ($r -ne 'definido') { $r | Out-File -FilePath $Saida -Encoding UTF8; exit 1 }
}
[ModoConsole]::Ler([uint32]$Alvo) | Out-File -FilePath $Saida -Encoding UTF8
