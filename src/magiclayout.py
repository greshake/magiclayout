""" A layout engine for i3 or sway. Allows saving of layouts, restoring and viewing the layout tree.

Usage:
  magiclayout.py magic [--db=<database_file>]
  magiclayout.py show [--json]
  magiclayout.py restore <layout>
  magiclayout.py save <layout>
  magiclayout.py -h | --help | --version
"""
import os
import re
from time import sleep

from docopt import docopt
from i3ipc import Event, Connection, Con
from i3ipc.events import IpcBaseEvent, BindingEvent

from layout import Layout
import i3ipc
import json

from restore import restore

if __name__ == '__main__':
    arguments = docopt(__doc__, version='0.1.1rc')

    connection = i3ipc.Connection()

    current_layout: Layout = \
        Layout.from_workspace(connection,
                              connection.get_tree().find_focused().workspace().name)

    if arguments['show']:
        if arguments['--json']:
            print(json.dumps(current_layout.to_json(), indent=2))
        else:
            print(current_layout)

    elif arguments['restore']:
        layout_name = arguments['<layout>']
        with open(f'{layout_name}.json', 'r') as f:
            layout_json = json.load(f)
        layout = Layout.from_json(connection, layout_json)
        print(f"Current layout:\n{current_layout}")
        print(f"Restoring layout:\n{layout}")
        layout.match_windows()
        print(f"Matched all windows:\n{layout}")
        restore(layout)

    elif arguments['save']:
        layout_name = arguments['<layout>']
        with open(f'{layout_name}.json', 'w') as f:
            json.dump(current_layout.to_json(), f, indent=4)
        print(f'Saved layout to {layout_name}.json')

    elif arguments['magic']:
        # The database stores the different seen layouts per workspace and per app signature.
        db_file = arguments['--db'] or 'database.json'
        # Read the database
        # if the file is empty, create a new file
        if not os.path.exists(db_file):
            with open(db_file, 'w') as f:
                json.dump({}, f)

        with open(db_file, 'r') as f:
            database = json.load(f)


        def commit():
            with open(db_file, 'w') as f:
                json.dump(database, f)


        # Subscribe to changes in the tree
        trigger_commands = ["move", "swap", "resize", "split", "layout", "mode"]

        def save_layout(layout: Layout):
            print(f"Saving layout:\n{layout}")

            # Find database entry for the current workspace
            workspace = layout.workspace
            if workspace not in database:
                database[workspace] = {}

            # Override database entry for the current app signature
            app_signature = layout.signature()
            database[workspace][app_signature] = layout.to_json()
            commit()

        def on_layout_changes(_, event: BindingEvent):
            global current_layout, database

            # Easier for debugging
            if "focus" in event.binding.command:
                return

            if not any(trigger_command in event.binding.command for trigger_command in trigger_commands):
                return

            sleep(0.005)  # Wait for the event to be processed

            current_layout = \
                Layout.from_workspace(connection,
                                      connection.get_tree().find_focused().workspace().name)

            if "move container to workspace" in event.binding.command:
                # When moving a window to a new workspace, we want to
                # arrange the windows on that workspace and the old one
                # instead of saving anything

                # The workspace name comes after the command, and may or may not
                # be enclosed in quotes. Examples:
                # "move container to workspace " #1 "
                # "move container to workspace 1"
                # "move container to workspace "1"
                # "move container to workspace \"1\""
                new_ws_regex = r"move container to workspace\s*(?P<ws_first>\"(?P<ws_alt>[^\"]*)\"|\w*)"
                new_ws_match = re.search(new_ws_regex, event.binding.command)
                result = new_ws_match.group('ws_first') if not new_ws_match.group('ws_alt') else new_ws_match.group(
                    'ws_alt')

                # Arrange the new WS
                on_new_or_closed_window(None, None, workspace=result)

                # Arrange the old WS
                on_new_or_closed_window(None, None)
            # IF we move a workspace to a different output, we want to update it there
            elif 'move workspace to output' in event.binding.command:
                on_new_or_closed_window(None, None, workspace=connection.get_tree().find_focused().workspace().name)
            else:
                save_layout(current_layout)

        connection.on(Event.BINDING, on_layout_changes)

        def on_new_or_closed_window(_, __, workspace=None):
            sleep(0.005)

            current_layout = \
                Layout.from_workspace(connection,
                                      connection.get_tree().find_focused().workspace().name
                                      if not workspace else workspace)

            # Find database entry for the current workspace
            workspace = current_layout.workspace
            if workspace not in database:
                database[workspace] = {}

            # Find database entry for the current app signature
            app_signature = current_layout.signature()
            if app_signature in database[workspace]:
                # Restore the layout
                layout = Layout.from_json(connection, database[workspace][app_signature])
                print(f"Resoring layout:\n{layout}")

                # Match windows
                layout.match_windows()

                # Ensure we still retain the focused window
                focused: Con = connection.get_tree().find_focused()

                # Restore the layout
                restore(layout)

                # Focus the window that was focused before
                focused.command("focus")
            else:
                print(f"No layout found for {app_signature}")

                # Saving new layout
                save_layout(current_layout)


        connection.on(Event.WINDOW_NEW, on_new_or_closed_window)
        connection.on(Event.WINDOW_CLOSE, on_new_or_closed_window)

        connection.main()
