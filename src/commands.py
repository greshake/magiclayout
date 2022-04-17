from typing import Union

import i3ipc

from layout import Layout
from nodes import LayoutNode, SplitContainer, WindowContainer, Container


class Command:
    def __init__(self, command: str, target: Union[LayoutNode, None] = None):
        self.command = command
        self.target = target

    def execute(self, connection: i3ipc.Connection) -> None:
        if self.target is not None:
            print(f"Executing command: \"[con_id={self.target.con_id}] {self.command}\"")
            current_con = self.target.get_con(connection)
            if current_con is not None:
                results = self.target.get_con(connection).command(self.command)
            else:
                print(f"Target window closed")
                results = []
        else:
            print(f"Executing command: \"{self.command}\"")
            results = connection.command(self.command)

        for i, result in enumerate(results):
            if result.success:
                print(f"-> OK")
            else:
                print(f"-> FAIL: {result.error}")
        if any(not result.success for result in results):
            print("A Command failed.")
            exit(1)

    def __str__(self):
        if self.target is not None:
            return f"\"[con_id={self.target.con_id}] {self.command}\""
        else:
            return f"\"{self.command}\""

    def __eq__(self, other):
        return self.command == other.command and self.target == other.target

    def simulate(self, layout: 'Layout') -> bool:
        return True


class MoveTo(Command):
    def __init__(self, target: LayoutNode, other: LayoutNode):
        super().__init__(f"move window to mark [con_id={other.con_id}]", target)
        self.other = other

    def execute(self, connection: i3ipc.Connection) -> None:
        # our move "target" is the "other" node

        # Mark other
        mark_cmd = Command("mark target", self.other)
        mark_cmd.execute(connection)

        # Move
        self.command = "move window to mark target"
        super().execute(connection)

        # Unmark other
        unmark_cmd = Command("unmark target", self.other)
        unmark_cmd.execute(connection)

    def simulate(self, full_layout: 'Layout'):
        layout = full_layout.root
        this: Container = layout.get_node_by_con_id(self.target.con_id)
        destination: Container = layout.get_node_by_con_id(self.other.con_id)

        if this == destination or this.has_ancestor(destination) or destination.has_ancestor(this):
            raise RuntimeError("Can not move to a descendant.")

        old_parent: Container = this.parent

        # Impl based on sway src
        this.detach()

        if isinstance(destination, WindowContainer):
            destination.add_sibling(this)
        else:
            destination.add_child(this)

        old_parent.reap_empty()


class Swap(Command):
    def __init__(self, target: LayoutNode, other: LayoutNode):
        super().__init__(f"swap container with con_id {other.con_id}", target)
        self.other = other

    def simulate(self, full_layout: Layout):
        layout = full_layout.root
        this: Container = layout.get_node_by_con_id(self.target.con_id)
        other: Container = layout.get_node_by_con_id(self.other.con_id)

        assert this is not None and other is not None

        if this.has_ancestor(other) or other.has_ancestor(this):
            # raise RuntimeError("Cannot swap ancestor and descendant.")
            return

        my_old_parent = this.parent
        other_old_parent: Container = other.parent

        this.parent.children.insert(this.parent.children.index(this), other)
        other.parent.children.insert(other.parent.children.index(other), this)
        this.parent.children.remove(this)
        other.parent.children.remove(other)
        other.parent = my_old_parent
        this.parent = other_old_parent


class Split(Command):
    def __init__(self, target: LayoutNode, orientation: str):
        super().__init__(f"split {orientation}", target)

        if orientation not in ["vertical", "horizontal", "none"]:
            raise ValueError(f"Invalid orientation: {orientation}")

        self.orientation = orientation

    def simulate(self, full_layout: Layout):
        layout = full_layout.root
        this: Container = layout.get_node_by_con_id(self.target.con_id)

        match self.orientation:
            case "vertical" | "horizontal":
                if this.parent is not None:
                    # Container Split
                    siblings = this.parent.children
                    if len(siblings) == 1:
                        this.parent.layout = 'splith' if self.orientation == 'horizontal' else 'splitv'
                        return
                    new_split = SplitContainer('splith' if self.orientation == 'horizontal' else 'splitv', [this])
                    this.replace(new_split)
                    return
                else:
                    # WS Split
                    new_split = SplitContainer('splith' if self.orientation == 'horizontal' else 'splitv',
                                               children=this.children)
                    for child in new_split.children:
                        child.parent = new_split
                    this.children = [new_split]
                    new_split.parent = this
            case "none":
                this.parent.flatten()


class Layout(Command):
    def __init__(self, target: LayoutNode, layout: str):
        super().__init__(f"layout {layout}", target)
        self.layout = layout

    def simulate(self, full_layout: Layout):
        layout = full_layout.root
        this: Container = layout.get_node_by_con_id(self.target.con_id)
        assert this is not None

        # Operate on the parent
        if this.parent:
            this = this.parent

        if this.layout != self.layout:
            if this.parent is not None:
                # Working with a non-workspace container
                this.layout = self.layout
            else:
                new_split = SplitContainer(this.layout,
                                           children=this.children)
                for child in new_split.children:
                    child.parent = new_split
                this.children = [new_split]
                new_split.parent = this


class Move(Command):
    def __init__(self, target: LayoutNode, direction: str):
        super().__init__(f"move {direction}", target)
        self.direction = direction
        assert direction in ["up", "down", "left", "right"]

    def simulate(self, full_layout: Layout):
        layout = full_layout.root
        container: Container = layout.get_node_by_con_id(self.target.con_id)
        old_parent: Container = container.parent
        assert container is not None

        if not container.move(self.direction):
            # Container didn't move
            return

        if old_parent:
            old_parent.reap_empty()


# Does not need to be simulated
class Resize(Command):
    def __init__(self, target: LayoutNode, rect: dict):
        super().__init__(f"resize set {rect['width']} px {rect['height']} px", target)
        self.rect = rect
        assert 0.0 <= rect['percent'] <= 1.0
        assert rect['width'] >= 0 and rect['height'] >= 0


def get_commands(node: LayoutNode) -> list[Command]:
    commands = []

    if not node.parent:
        return commands

    # Layout commands
    for layout in ["splitv", "splith", "stacked", "tabbed"]:
        commands.append(Layout(node, layout))

    # Swap commands
    dependent_nodes = set(node.nodes()).union(set(node.parents()))
    for other in set(node.root().nodes()) - dependent_nodes:
        if other:
            commands.append(Swap(node, other))
            commands.append(MoveTo(node, other))

    # Split commands
    for direction in ["vertical", "horizontal", "none"]:
        commands.append(Split(node, direction))

    # Move commands
    for direction in ["up", "down", "left", "right"]:
        commands.append(Move(node, direction))

    return commands
