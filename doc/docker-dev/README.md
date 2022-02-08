# Development container for NEBUALA project
## Build guide:
Before starting: make sure you have the remote-ssh and remote-containers extensions installed
- open the project in ssh after cloning
- at the top level (it not exists) create a folder called '.devcontainer' (or F1 >> 'Remote-Containers: Add Development Container Configuration Files…')
- copy the files under doc/docker-dev/files to .devcontainer folder. you can add extra packages to environment.yml
- F1 >> 'Remote-Containers: open folder in container'
- Make some coffee, it will take time...
- After the vscode will opens in the container, you need to select the correct python interpreter:
  F1 >> Python: select interpreter - choose the one that point to ('base) conda
- if you need to add more packages, just add them to environment.yml and choose F1 >> 'Remote-Containers: rebuild containers'
## Notes:
- in .gitignore add .devcontainer to avoid commiting this folder (as well as .vscode)
- the conda running env is base
