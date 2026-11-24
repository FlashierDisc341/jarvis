# JARVIS v9: read-only PC reports

Adds the agreed CPU/RAM/disk reporting batch. Notes, reminders and maths stay intact.
Temperatures, GPU readings, in-app controls and conversational AI are not added.

## Install

Stop JARVIS with Ctrl+C.

REPLACE these existing files in the Jarvis folder:
- jarvis_actions.py
- jarvis_help.py

ADD:
- jarvis_monitor.py
- test_monitor.py

Keep the working v8 jarvis_whisper.py, jarvis_dialogue.py, jarvis_organizer.py,
all audio/model/voice files, all maths files and the rest of the existing modules.
Do not remove or replace the data folder or organizer database.

There is no additional pip installation for this batch.
It uses the psutil package already installed for app lifecycle controls.

Run:

    .\.venv-whisper\Scripts\python.exe test_monitor.py

These are MOCKED tests, not a live benchmark. They cover:
- Command recognition and leaving unrelated commands alone.
- CPU capacity normalization and combining multiple executable instances.
- Combined app working sets and partial/unavailable readings.
- Correct Windows-drive selection, without assuming C:.
- PID-reuse, executable-path and session-change rejection.
- Windows dispatcher choices, no launch/close calls from report commands,
  and preserving literal note dictation.

This build has been reviewed but NOT executed in the author's environment.
If tests fail, keep their full output rather than proceeding.

Optional checks for the features that were already working:

    .\.venv-whisper\Scripts\python.exe test_organizer.py
    .\.venv-whisper\Scripts\python.exe test_math.py

After the new tests report OK, start normally:

    .\.venv-whisper\Scripts\python.exe jarvis_whisper.py

Do not use --dry-run if you want spoken reports.

## Voice checks

- "Jarvis, system report."
- "Jarvis, CPU usage."
- "Jarvis, RAM usage."
- "Jarvis, how much disk space is free?"
- "Jarvis, how much memory is Chrome using?"
- "Jarvis, what's using the most CPU?"

Also:
- pc status / pc report / system status / resource report
- how much RAM does Discord use
- memory usage for FL Studio 2026
- help with system
- repeat that

The existing "status report" still gives the older voice/app-catalogue status.
Use "system report" for the new hardware/resource report.

For app memory, the app must have matching readable running processes.
Ambiguous names get numbered choices. Different executable paths are different
groups, even if their friendly names match. The process-group ID in the choice
label helps distinguish otherwise identical names. No app is launched to obtain
a report.

## What the values actually mean

### System CPU

A one-second system-wide CPU utilization sample, not the meaningless first
non-blocking call. It is a percentage of the whole machine's CPU capacity.
The report is a short snapshot, not a long-term average or a diagnosis.

### System RAM

Reports used percentage derived from total minus available, plus available and
total physical RAM. Available is the relevant reclaimable/usable amount; it is
not merely completely empty memory.

### Disk

Reads free/total space only on the drive identified by the running process's
Windows SystemRoot. It does not assume Windows is on C:, scan files, search other
drives, delete anything or "clean" storage. If the drive cannot be established or
read, that reading is unavailable rather than an invented zero.

### App memory

Adds RSS/Windows working-set bytes for readable processes from the SAME executable
path in the current user's Windows session. Chrome renderers using that executable
are combined. Multiple profiles using the same executable are combined too.

This is NOT unique RAM consumption or Task Manager's default private-memory column.
Shared pages may be counted in more than one process. Separate helper executables
are not automatically attributed to an app. The spoken reply explicitly identifies
it as a combined working set.

Groups are found from executable/friendly names and matching Start-app catalogue
entries, not browser tab titles or document contents. Processes are identity-checked
again before/after reading a metric. Exited, inaccessible or reused PIDs are skipped.
A partial scan/readback is labelled partial. Discovery failures can make a report
conservatively partial even if the inaccessible process belonged to something else.
No match does not prove an app is absent.

### Largest CPU users

Ranks executable groups among readable processes in YOUR user/session, not every
system service or other user's workload. System/idle PIDs and other sessions are
excluded. The reply names this limited scope.

Takes a cumulative user+kernel CPU-time baseline for each captured process, waits
one second, and reads it again. Each process uses its own actual elapsed interval.
Its share is divided by the logical CPU count before grouping, so percentages are
relative to total logical CPU capacity rather than one core.

The top three non-negligible groups are spoken; up to ten print in the terminal.
Counts, skipped readings and actual sample intervals also print locally.
A quiet sample means the measured groups were quiet, not that inaccessible services
or the entire PC used no CPU. Processes born/exited during the sample can be missed.

Task Manager may use different grouping, timing and CPU-frequency normalization.
Do not expect identical values or assume a high value proves an app is broken.

## Units and timing

Memory and storage use binary units:
- one mebibyte = 1,048,576 bytes
- one gibibyte = 1,073,741,824 bytes

These are labelled explicitly instead of mislabelling binary sizes as decimal GB.

CPU sampling waits one second. Process enumeration/identity checks add overhead.
Each scan phase has a 2.5-second traversal budget; discovery also caps at 4,096 PIDs.
Individual OS calls are not forcibly timed out. Exceeding a traversal budget gives
a partial report rather than silently treating the incomplete list as complete.

As with other actions, the microphone is paused during the report and its speech.
Timers/reminders may be announced afterwards if they became due during sampling.
This is on-demand reporting, not continuous monitoring or a real-time alarm.

## Read-only boundary

The reporting code does not kill, close, focus or start apps, change priorities,
adjust settings, elevate privileges, save a metrics log or send readings online.
It uses process metadata and counters, not file contents, command lines, URLs,
window text, credentials or browsing history.

Normal existing JARVIS controls still exist as separate commands.
These new reporting commands do not automatically invoke them.
Speech recognition is unchanged and can still mishear a command.

## Optional standalone read-only check

This prints just the live system-wide CPU/RAM/Windows-drive report without voice:

    .\.venv-whisper\Scripts\python.exe jarvis_monitor.py

It is not the mocked test suite; the numbers come from your running PC.

## Primary reference

The installed dependency's documentation covers CPU sampling, process CPU counters,
RSS/working set, available physical memory and disk usage:
https://psutil.io/7.2/
