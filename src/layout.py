import hashlib
import json

from nodes import *


class Layout:
    """
    Represents an i3/sway window tree (based on LayoutNodes).

    Layouts are fixed to a workspace and output. They can be matched to windows
    on the workspace and used to restore the layout or save it.
    """

    def __init__(self, connection: i3ipc.Connection, workspace: str):
        """
        Create a new empty layout for the given workspace.
        :param workspace: The name of the workspace.
        """
        self.workspace = workspace
        self.connection = connection
        outputs = connection.get_outputs()

        for output in outputs:
            if output.current_workspace == workspace:
                self.output = output.name
        self.root: Union[LayoutNode, None] = None

    def match_windows(self):
        """
        Match windows to the layout.
        """
        if not self.root:
            raise Exception("No root node in layout")

        unmatched_leaves = list(Layout.from_workspace(self.connection, self.workspace).root.leaves())

        if len(unmatched_leaves) == 1 and isinstance(unmatched_leaves[0], SplitContainer):
            raise Exception(f"Workspace \"{self.workspace}\" is empty")

        for leaf in self.root.leaves():
            if len(unmatched_leaves) == 0:
                raise Exception("Not enough windows to match layout, missing: " + str(list(self.root.leaves())))
            elif leaf.con_id:
                unmatched_leaves.remove(leaf)
            else:
                for unmatched_leaf in unmatched_leaves:
                    if leaf.swallows(unmatched_leaf):
                        leaf.con_id = unmatched_leaf.con_id
                        unmatched_leaves.remove(unmatched_leaf)
                        break

        if len(unmatched_leaves) > 0:
            raise Exception("Can't match all windows to layout, remaining: " + repr(unmatched_leaves))

    def app_signature(self):
        """
        Get the signature of the layout.
        :return: dict
        """
        counter = {app.name(): 0 for app in self.root.leaves()}
        for app in self.root.leaves():
            counter[app.name()] += 1
        return counter

    def signature(self):
        """
        Get an MD5 hash of the app signature.
        :return: str
        """
        return hashlib.md5((json.dumps(self.app_signature(), sort_keys=True) +
                            self.output)
                           .encode()).hexdigest()

    @classmethod
    def from_json(cls, connection: i3ipc.Connection, json_data: dict, workspace=None):
        """
        Create a new layout from the given json data. Defaults to the saved workspace, but can be overwritten.
        :param connection: The i3 connection.
        :param json_data: The json data.
        :param workspace: The workspace to use. (Optional)
        :return: Layout
        """
        layout = Layout(connection, json_data["workspace"])
        layout.root = LayoutNode.from_json(json_data["root"])
        return layout

    def to_json(self):
        """
        Convert the layout to json data.
        :return: dict
        """
        return {
            "workspace": self.workspace,
            "root": self.root.to_json()
        }

    @classmethod
    def from_workspace(cls, connection: i3ipc.Connection, workspace):
        """
        Create a new layout from the given workspace.
        :param workspace: The workspace to use.
        :return: Layout

        :param connection: The i3 connection.
        :param workspace: The workspace to use.
        :return: Layout
        """
        ws_con = connection.get_tree().find_named(workspace)

        if len(ws_con) == 0:
            raise ValueError(f"Workspace {workspace} not found")

        ws_con = ws_con[0]

        layout = Layout(connection, workspace)
        layout.root = LayoutNode.from_con(ws_con)

        return layout

    def __str__(self):
        """
        For printing the layout to the console for the end user.
        :return: str
        """
        result = f"Layout for workspace \"{self.workspace}\" on output {self.output}\n"

        def _str_node(node, indent=0):
            s = f"{' ' * indent}{str(node)}\n"

            for child in node.children:
                s += _str_node(child, indent + 2)

            return s

        return result + _str_node(self.root)

    def __repr__(self):
        """
        For debugging purposes.
        :return: str
        """
        return f"Layout(workspace={self.workspace}, root={repr(self.root)})"
