# Startet Hermes CRM (Backend + Frontend) und oeffnet den Browser-Tab.
# Gedacht fuer das Desktop-Icon - prueft zuerst, ob die Server schon laufen
# (z.B. aus einer frueheren Claude-Code-Session), um keine doppelten
# Prozesse auf denselben Ports zu starten.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Test-PortOpen($port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect("127.0.0.1", $port)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

# WICHTIG: ein Fehler beim Start EINER Komponente (z.B. Frontend-Start
# schlaegt fehl, weil pnpm im PATH bei einem ganz frischen Login/Systemstart
# noch nicht aufgeloest werden kann) darf nicht den ganzen Rest des Skripts
# abbrechen (mit $ErrorActionPreference="Stop" sonst der Fall) - sonst laeuft
# z.B. das Backend bereits (unsichtbar) weiter, aber der Browser wird nie
# geoeffnet und das Fenster schliesst sich kommentarlos ("PowerShell oeffnet
# und schliesst direkt"). Deshalb hier try/catch statt globalem Stop, mit
# klarer Fehlermeldung pro Komponente.

if (-not (Test-PortOpen 8000)) {
    Write-Host "Starte Backend..."
    try {
        # WICHTIG: Start-Process -ArgumentList mit einem Array quotet Elemente
        # mit Leerzeichen NICHT automatisch (anders als beim direkten Aufruf
        # ueber die Konsole) - der Projektpfad enthaelt Leerzeichen ("OneDrive
        # - Commandeur Consulting GmbH"), wodurch uvicorn den Pfad als mehrere
        # kaputte Extra-Argumente sah und sofort mit einem Fehler abbrach.
        # Deshalb hier ein einzelner, selbst gequoteter Argument-String statt
        # eines Arrays.
        # KEIN --reload hier: der WatchFiles-Reloader-Supervisor haengt sich
        # zuverlaessig auf, wenn er ueber ein per Start-Process gestartetes,
        # minimiertes/konsolenloses Fenster laeuft (Migration/Alembic-Log wird
        # noch ausgegeben, aber "Application startup complete" kommt nie - der
        # Health-Check haengt fuer immer). Ohne --reload startet der Server
        # zuverlaessig; Auto-Reload braucht ohnehin nur, wer aktiv am Code
        # arbeitet (dort direkt im Terminal starten, nicht ueber das Icon).
        $backendArgs = "-m uvicorn cc_crm.main:app --app-dir `"$root\backend\src`" --host 127.0.0.1 --port 8000"
        Start-Process -WindowStyle Minimized -FilePath "$root\backend\.venv\Scripts\python.exe" `
            -ArgumentList $backendArgs -WorkingDirectory $root -ErrorAction Stop
    } catch {
        Write-Host "FEHLER beim Backend-Start: $_"
    }
} else {
    Write-Host "Backend laeuft bereits auf Port 8000."
}

if (-not (Test-PortOpen 3000)) {
    Write-Host "Starte Frontend..."
    try {
        # Vollen Pfad zu pnpm.cmd statt nur "pnpm.cmd" verwenden - unmittelbar
        # nach einem frischen Login/Systemstart ist PATH-Aufloesung ueber
        # Start-Process nicht immer sofort verlaesslich, ein absoluter Pfad
        # umgeht das komplett. "pnpm" (ohne Endung) fuehrt ausserdem zu einem
        # nicht ausfuehrbaren Shim ("%1 ist keine zulaessige
        # Win32-Anwendung") - pnpm.cmd ist die richtige Datei.
        $pnpmCmd = (Get-Command pnpm.cmd -ErrorAction SilentlyContinue).Source
        if (-not $pnpmCmd) {
            $pnpmCmd = "$env:APPDATA\npm\pnpm.cmd"
        }
        $frontendArgs = "--dir `"$root\frontend`" dev"
        Start-Process -WindowStyle Minimized -FilePath $pnpmCmd -ArgumentList $frontendArgs `
            -WorkingDirectory $root -ErrorAction Stop
    } catch {
        Write-Host "FEHLER beim Frontend-Start: $_"
    }
} else {
    Write-Host "Frontend laeuft bereits auf Port 3000."
}

Write-Host "Warte, bis das CRM erreichbar ist..."
# 180s statt frueher 60s: bei einem frischen Systemstart (Laptop war aus)
# scannt der Virenschutz die frisch gestarteten python.exe/node.exe-Prozesse
# und alle geladenen Module einmalig deutlich langsamer - das kann den
# Backend-Start auf ueber eine Minute strecken, obwohl er nicht haengt
# (das Konsolenfenster zeigt in der Zeit einfach keine neue Zeile an und
# sieht dadurch eingefroren aus). 60s hat in diesem Fall nicht gereicht und
# der Browser wurde zu frueh (oder gar nicht sichtbar) geoeffnet.
$maxWaitSeconds = 180
$ready = $false
for ($i = 0; $i -lt $maxWaitSeconds; $i++) {
    if ((Test-PortOpen 8000) -and (Test-PortOpen 3000)) {
        $ready = $true
        break
    }
    if ($i % 15 -eq 0 -and $i -gt 0) {
        Write-Host "  ... immer noch am Starten (${i}s), das kann bei einem frischen Systemstart etwas dauern."
    }
    Start-Sleep -Seconds 1
}

if (-not $ready) {
    Write-Host "Backend/Frontend antworten nach ${maxWaitSeconds}s noch nicht - oeffne trotzdem den Browser."
}

Start-Process "http://localhost:3000"
