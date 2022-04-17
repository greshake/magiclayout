# magiclayout
Repetitively arranging windows on a tiling WM is annoying. No more! Install one binary to give your WM a brain. 

**This is proof-of-concept-level software.**
If you really would like to give it a try (currently sway is supported with i3 just not tested) please have a look at the prototype branch. The prototype is written in Python and will hog your resources unreasonably, so use it for testing only. It works on my daily driver as of right now, but it may break anytime. If you want to contribute to the development of the main project please give me feedback on the higher-level features, options and extensions you want to see. I'm particularly interested how it affects your workflow, and in what cases you find it more disruptive then helpful. Or tell me which WMs and platforms you would like to see supported or implement yourself. The prototype code is horrible and will be incinerated as soon as feasible. Dive in with caution.


# General Idea
When you make changes to your window layout, your WM should remember the setup and apply it the next time automatically, without any configuration. It should be capable of learning from your everyday usage and make you more productive!

# How does it work?
magiclayout runs in the background and observes your WM usage over the IPC API. When you open or close windows, move windows between workspaces or move workspaces to different outputs magiclayout will look for a matching layout that has been seen on that output/workspace before, and apply it. Whenever you actually intentionally make a change such as resizing containers, changing orientations or moving them, magiclayout will take a snapshot of that layout on the current workspace and output. The resulting layout will be assigned a hash and stored in a database.
The database persists even between reboots and keeps growing with you. At any time you can reset the database, or enable/disable magiclayout while your WM is running.
