---
name: Bug report
about: Report a problem in pympress
title: ''
labels: ''
assignees: ''

---

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Screenshots**
If applicable, add screenshots to help explain your problem.

**Environment (please complete the following information):**
 - OS: [e.g. Ubuntu]
 - Python version: [e.g. 3.9]
 - Pympress version: [e.g. 1.5.0]
 - Installation method: [e.g. source, pip, binary installer, chocolatey, copr, other package manager]

**Debug information (see below for file locations)**
 - What is reported in pympress.log?
 - Does the problem still happen if you remove your config file?
   (You can just move the config file to a different location to be able to restore it after testing)


**Additional context**
Add any other context about the problem here.


<!-- --------------------------------------------------------------------------------------------------

The pympress config and log locations are given in the pop-up available through the Help > about menu.

The **log file** is located in the user cache folder, thus one of the following locations:
On Linux:

    $XDG_CACHE_HOME/pympress.log
    ~/.cache/pympress.log

On macOS:

    ~/Library/Logs/pympress.log

On Windows:

    %LOCALAPPDATA%\pympress.log
    %APPDATA%\pympress.log

The **config file** is located in the user preference folder, thus one of the following locations:
On Linux:

    $XDG_CONFIG_HOME/pympress
    ~/.config/pympress

On macOS:

    ~/Library/Preferences/pympress

On Windows:

    %APPDATA%\pympress.ini

--------------------------------------------------------------------------------------------------  -->
