### Environment
- Operating system and version
- Python version

### Pympress
- version
- Installation method: source, pip, binary installer, chocolatey, copr, other package manager?

### Expected behaviour
What are you trying to achieve? What's the expected outcome?

### Steps to reproduce
What are you doing?

### Problem
What's happening instead of what you are expecting?

What is reported in pympress.log?\*

Does the problem still happen if you remove your config file?\*
(You can just move the config file to a different location to be able to restore it after testing)

--------------------------------------------------------------------------------------------------

\* The pympress config and log locations are given in the pop-up available through the Help > about menu item.

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
