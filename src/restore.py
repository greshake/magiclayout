import copy

from layout import Layout
from commands import get_commands, Resize

COMMAND_LIMIT = 50


def restore(target_layout: Layout):
    """
    Restore the layout to the workspace. For now, only works if all
    leaf windows are matched to concrete windows.

    Also the algortihm I use is some weird hill climb variation that can get stuck.
    I didn't manage inductively reasoning about i3/sway semantics to get a
    linear-time  direct transform algorithm to work reliably. So now I just simulate
    all applicable commands and try to get as close as possible. Unfortunately the number of
    applicable commands scales in O(n²)  worst-case for number of containers so this is not
    a permanent solution. i3 still had a built-in layout restore feature we could use,
    but sway insists on letting us do it via the IPC commands.

    :return: Success (bool)
    """

    assert all(leaf.matched() for leaf in target_layout.root.leaves())

    print("\nStarting to restore layout")

    actual_layout = Layout.from_workspace(target_layout.connection, target_layout.workspace)
    similarity = target_layout.root.compare(actual_layout.root)

    count = 0

    while count < COMMAND_LIMIT:
        print(f"Action {count}. Similarity: {similarity}")

        # Collect all possible actions
        commands = []
        for node in actual_layout.root.nodes():
            for cmd in get_commands(node):
                if cmd not in commands:
                    commands.append(cmd)
        print(f"Collected {len(commands)} commands, Ranking...")

        # Simulate and rank all possible actions
        all_commands = []
        ranked_commands = []
        fallback_commands = []  # commands that reduce the number of nodes but do not change the score
        for command in commands:
            # Make a deep copy of the actual layout
            outcome_root = copy.deepcopy(actual_layout.root)
            outcome = Layout(target_layout.connection, target_layout.workspace)
            outcome.root = outcome_root

            # Simulate the action
            command.simulate(outcome)

            simulated_similarity = target_layout.root.compare(outcome.root)
            all_commands.append((simulated_similarity, command, outcome))
            if simulated_similarity > similarity:
                ranked_commands.append((simulated_similarity, command, outcome))
                if len(ranked_commands) > 15:
                    break
            elif simulated_similarity == similarity and actual_layout.root.count_nodes() > outcome.root.count_nodes():
                fallback_commands.append((outcome.root.count_nodes(), command, outcome))

        print(f"Ranking done, {len(ranked_commands)} actions possible and improving similarity")

        # Sort the actions by similarity
        ranked_commands.sort(key=lambda x: x[0], reverse=True)
        fallback_commands.sort(key=lambda x: x[0])  # sort by number of nodes- we want to get rid of as many as we can

        if len(ranked_commands) == 0:
            print(f"No actions possible, falling back to fallback commands (count: {len(fallback_commands)})")
            ranked_commands = fallback_commands

        if len(ranked_commands) == 0:
            print("No more applicable actions, stopping")
            break

        # Choose the best action
        print("Best 5 actions:")
        for i in range(min(5, len(ranked_commands))):
            print(f"{i + 1}. {round(ranked_commands[i][0])} {ranked_commands[i][1]}")

        # Apply the action
        print("Applying best action. Predicted Layout:")
        best_similarity, best_command, best_outcome = ranked_commands[0]
        print(best_outcome)
        best_command.execute(target_layout.connection)
        count += 1

        # Refresh the new layout, and ensure it matches the simulated tree
        actual_layout = Layout.from_workspace(target_layout.connection, target_layout.workspace)
        similarity = target_layout.root.compare(actual_layout.root)

        if not best_outcome.root.equal_precise(actual_layout.root):
            print("Simulated action did not match the predicted outcome! Actual layout:")
            print(actual_layout)

    # Check if the layout is correct
    if not target_layout.root.equal_precise(actual_layout.root):
        print("Target layout did not match the actual layout!")
        return

    print("Layout is correct!")
    print("Correcting the size of containers")

    def close(a, b):
        # Allow a 10% variation in size. Otherwise it might look a bit glitchy
        # when we adjust windows by a few pixels.
        return abs(a - b) < 0.1

    # The resizing algorithm comes from https://github.com/swaywm/sway/pull/6435
    for leaf in target_layout.root.leaves():
        con = leaf.get_con(target_layout.connection)

        if not con:
            print(f"Could not find container for leaf {leaf}, cancelling")
            return

        if not close(con.rect.width, leaf.rect['width']) or \
                not close(con.rect.height, leaf.rect['height']):
            print(f"Resizing {con.name[-20:]} from {con.rect.width}x{con.rect.height} "
                  f"to {leaf.rect['width']}x{leaf.rect['height']}")
            Resize(leaf, leaf.rect).execute(target_layout.connection)

        leaf.parent.con_id = con.parent.id
        while leaf.parent is not None and leaf.parent.rect['percent'] is not None:
            con = leaf.parent.get_con(target_layout.connection)

            if not con:
                print(f"Could not find container for leaf's parent {leaf.parent}, cancelling")
                return

            if not close(con.rect.width, leaf.parent.rect['width']) or \
                    not close(con.rect.height, leaf.parent.rect['height']):
                Resize(leaf.parent, leaf.parent.rect).execute(target_layout.connection)

            leaf = leaf.parent
            if leaf.parent:
                leaf.parent.con_id = leaf.get_con(target_layout.connection).parent.id
