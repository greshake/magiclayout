# magiclayout
Repetitively arranging windows on a tiling WM is annoying. No more! Install one binary to give your WM a brain. 

Prototype supports Sway and potentially i3 (untested).

**This is proof-of-concept-level software.**
The prototype is written in Python and will hog your resources unreasonably, so use it for testing only. It works on my daily driver as of right now, but it may break anytime. If you want to contribute to the development of the main project please give me feedback on the higher-level features, options and extensions you want to see. I'm particularly interested how it affects your workflow, and in what cases you find it more disruptive then helpful. Or tell me which WMs and platforms you would like to see supported or implement yourself. The prototype code is horrible and will be incinerated as soon as feasible. When I think I have a good grasp on the real-world usage for the prototype, I'll build the main project in Rust.


# General Idea
When you make changes to your window layout, your WM should remember the setup and apply it the next time automatically, without any configuration. It should be capable of learning from your everyday usage and make you more productive!

# How does it work?
magiclayout runs in the background and observes your WM usage over the IPC API. When you open or close windows, move windows between workspaces or move workspaces to different outputs magiclayout will look for a matching layout that has been seen on that output/workspace before, and apply it. Whenever you actually intentionally make a change such as resizing containers, changing orientations or moving them, magiclayout will take a snapshot of that layout on the current workspace and output. The resulting layout will be assigned a hash and stored in a database.
The database persists even between reboots and keeps growing with you. At any time you can reset the database, or enable/disable magiclayout while your WM is running.

# Running magiclayout
1. Clone this repository: `git clone git@github.com:greshake/magiclayout.git`
2. Ensure you are running at least Python 3.10: `python --version`
3. Install the dependencies (might be pip3 for your distro): `pip install -r requirements.txt`
4. For debugging and testing, run `python src/magiclayout.py magic [--db=<path>]`

# Brave supporters
If you like magiclayout and the prototype works for you, 
all you need to do to use it in sway is adding the following line to 
your sway/i3 config:
```
exec --no-startup-id /path/to/magiclayout/startmagic.sh
```
The database is stored in `~/.config/magiclayout.db` by default. There is no other configuration.

Using it in i3 is not hard, but you need to stop the "split none" command from being generated at the end of commands.py
If you do, I have no idea if it still works. In the main program the i3 implementation will take advantage of i3's own 
layout restore features, making it much more reliable. I don't want to fix the hacky 
implementation for sway to work with i3 as it is wasted time anyway.