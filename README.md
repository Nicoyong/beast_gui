# BEAST GUI v2

BEAST GUI v2 est une interface graphique permettant de lancer des simulations BEAST avec une file d'attente et des fonctionnalités de pause/reprise automatiques sous Windows.

## Fonctionnalités

- **File d'attente** : Gère l'ordre de traitement des fichiers XML.
- **Pause/Reprise automatique** : Pause les calculs lorsque le PC est utilisé et reprends en cas d'inactivité prolongée.
- **Interface graphique intuitive** : Interface utilisateur simple pour gérer les paramètres BEAST.

## Prérequis

- **Python 3** : Assurez-vous que Python 3 est installé sur votre système avec l'option "Add python.exe to PATH".
- **psutil** : Installé automatiquement par le script `lancer_beast_gui.bat`.

## Installation

1. Téléchargez les fichiers du projet :
   - `config.yaml`
   - `beast_gui.py`
   - `beast_gui_settings.json`
   - `lancer_beast_gui.bat`

2. Placez ces fichiers dans un répertoire de votre choix.

3. Exécutez le script `lancer_beast_gui.bat` pour lancer l'interface graphique BEAST GUI v2 :
    ```shell
    lancer_beast_gui.bat
    ```

4. Pour voir les erreurs éventuelles, vous pouvez lancer le script en mode debug :
    ```shell
    lancer_beast_gui.bat debug
    ```

## Configuration

Les paramètres de configuration peuvent être modifiés directement dans le fichier `beast_gui_settings.json`. Voici un exemple des paramètres disponibles :

```json
{
  "bat": "D:\\Users\\Nicolas\\Desktop\\BEAST\\bat\\beast.bat",
  "mode": "CPU",            # "CPU" / "GPU" / "Aucun"
  "threads": 16,
  "resume": false,          # BEAST -resume
  "overwrite": false,       # BEAST -overwrite
  "working": true,          # BEAST -working
  "extra": "",
  "auto_pause": true,
  "pause_delay": 10,        # secondes d'utilisation avant la pause
  "auto_resume": true,
  "resume_minutes": 15,     # minutes d'inactivité avant la reprise
  "keyboard": true,         # compter aussi le clavier
  "continue_on_error": true,
  "beep": true,             # bip à la fin de la file
  "queue": []
}
```

## Utilisation

1. **Ajouter des fichiers XML** : Utilisez l'interface graphique pour ajouter les fichiers XML que vous souhaitez traiter.
2. **Configurer les paramètres BEAST** : Remplacez les options dans `beast_gui_settings.json` ou utilisez les champs correspondants dans l'interface graphique.
3. **Lancer la file d'attente** : Cliquez sur "Lancer la file" pour commencer le traitement des fichiers XML en respectant les paramètres définis.

## Contribuer

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou un pull request.

## Licence

Ce projet est sous licence MIT. Voir le fichier `LICENCE` pour plus de détails.