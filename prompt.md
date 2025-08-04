You are a great web dev. I want you to create an application from scratch called Lemonade Arcade. This app is a python FastAPI server that presents an html+javascript GUI in a web browser. LLMs are served to this app by Lemonade Server via OpenAI chat/completions API.

Lemonade Arcade will be a cross between a ChatGPT-like interface and the concept of a game emulator. Except it wont emulate any games. Instead, Lemonade Arcade will use an LLM to generate the game in response to a user's prompt, then start the game. 

Codegen rules (for the system prompt): Games should be coded in Python using the pygame library, in a single Python code block, with absolutely no images or other external files used.

User journey:
1. User obtains Lemonade Arcade by cloning this repo and running a setup.py.
1. User opens Lemonade Arcade by running "lemonade-arcade" in their activated python environment. This should start the FastAPI server and open the GUI in a browser.
1. User is presented with a html+js+css UI that includes:
    - a prompt entry box at the bottom. it should have text entry, a "send" button, and a model selection dropdown. Similar to any popular LLM app. The "send" button should be labeled "create game", not "send".
    - a "library" of generated games (game titles in rounded rectangles, like a grid of apps, but dont rely on any image assets).
    - a "side-car" on the right to show the LLM's output in real time
    - a status icon in the top-right to show if Lemonade Server is running or not. Provide a "Get Lemonade" link if it is not running, show a glowing lemon emoji if it is running.
    - At the top center, there should be "Lemonade Arcade" in some nice pixel/8bit/ASCII art.
    - DO NOT USE IMAGE ASSETS FOR ANY OF THIS. I don't want to have a lot of files in this project at this time.
    - Use a dark color theme common to arcades and emulators for this UI. It does not need to look like the typical Lemonade styling.
1. User enters a prompt describing a game, like "I want to play snake, but the food should move", and presses enter (or clicks a send button).
1. The LLM streams output into a side-car, and the user can watch this if they like while they wait. The main UI should show a "spinner" indicating progress is being made. The spinner should have status updates like "writing code".
1. Once code generation is done, the app should do the following:
    1. extract the Python code block from the LLM response.
    1. save the Python code block to a .py file with a unique name, representing a new game.
    1. add this new game as an icon to the "library" described in the UI above. clicking this icon should launch the game.
    1. launch the game by running the .py file using the project's sys.executable.
    1. show a status in the main UI like "game running" and don't let the user launch any new games until they close the prior game.
1. The user can start any game from their library by clicking the icon made in the previous step. 
    - Each icon should have an on-hover "X" button, which when clicked opens a "are you sure" dialog to delete the game. Deletion should remove the python file for that game, and the icon from the library.
