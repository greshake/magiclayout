from typing import Union

import i3ipc


def is_parallel(layout, direction):
    match layout:
        case 'splith':
            return direction == 'left' or direction == 'right'
        case 'splitv':
            return direction == 'up' or direction == 'down'
        case 'stacked':
            return direction == 'up' or direction == 'down'
        case 'tabbed':
            return direction == 'left' or direction == 'right'
        case _:
            raise ValueError(f'Unknown layout: {layout}')


class LayoutNode:
    """
    Every node is a container, and every container is either a split container or a leaf (window).

    The split containers can have different layouts (splith, splitv,
    tabbed, stacked) which are in the "layout" property.

    The leaf nodes have a special property called "swallows" which
    defines what windows can be matched to this container. Each swallow
    can match on the properties "class" (X11 windows), or "app_id"
    (wayland windows). Each property is a regular expression.

    If a container has the "con_id" property set, it has already been matched
    to a concrete window on the workspace now.
    """

    def __init__(self, children=None, con_id=None, parent=None, fake_id=None, rect=None):
        self.con_id = con_id
        self.fake_id = fake_id
        self.rect = rect
        self.parent = parent
        self.children = children or []
        self.expected: Union[None, Container] = None

    def get_con(self, connection: i3ipc.Connection):
        if self.con_id is not None:
            return connection.get_tree().find_by_id(self.con_id)
        else:
            return None

    def matched(self):
        return self.con_id is not None

    def leaves(self) -> list['WindowContainer']:
        """
        Generates all leaf nodes.
        """
        if len(self.children) == 0 and self.parent:
            yield self
        else:
            for child in self.children:
                yield from child.leaves()

    def container(self) -> 'SplitContainer':
        if isinstance(self, SplitContainer):
            return self
        else:
            return self.parent

    def root(self):
        if self.parent is None:
            return self
        else:
            return self.parent.root()

    def equal_precise(self, other: 'Container'):
        if self == other and len(self.children) == len(other.children):
            return all(c1.equal_precise(c2) for c1, c2 in zip(self.children, other.children))
        return False

    def parents(self):
        if self.parent is not None:
            yield self.parent
            yield from self.parent.parents()

    def add_sibling(self, other: 'Container', after: bool = True):
        """
        Add a sibling to the current container.
        """
        if self.parent is None:
            raise ValueError("Cannot add sibling to root container.")

        siblings = self.parent.children
        siblings.insert(siblings.index(self) + 1 if after else siblings.index(self), other)
        other.parent = self.parent

    def siblings(self):
        if self.parent is None:
            return []
        else:
            return self.parent.children

    def add_child(self, child: 'Container', index: int = None):
        """
        Add a child to the current container.
        """
        if not index:
            self.children.append(child)
        else:
            self.children.insert(index, child)
        child.parent = self

    # TODO: Move this into commands, doesn't really fit here
    def move(self, direction: str):
        offs = -1 if direction in ["left", "up"] else 1
        index = -1
        desired = -1

        siblings = None
        target = None

        # Look for a suitable ancestor of the container to move within
        ancestor: Union[None, Container] = None
        current = self
        wrapped = False

        while not ancestor:
            parent_layout = current.parent.layout

            if not is_parallel(parent_layout, direction):
                if not current.parent.parent:
                    # No parallel parent, so we reorient the workspace
                    # Wrap all the children
                    new_ws = current.root().workspace_wrap_children()
                    current.root().layout = 'splith' if direction in ['left', 'right'] else 'splitv'
                    current = new_ws
                    wrapped = True
                else:
                    current = current.parent
                continue

            #  Only scratchpad hidden containers don't have siblings
            #  so siblings != NULL here ---> False a bug is here
            siblings = current.siblings()
            index = siblings.index(current) if current in siblings else -1
            desired = index + offs
            target = None if desired == -1 or desired == len(siblings) else siblings[desired]

            if current == self:
                if target:
                    # // Container will swap with or descend into its neighbor
                    # container_move_to_container_from_direction(container,
                    # 						target, move_dir);
                    # 				return true;
                    return False
                    raise NotImplementedError()
                elif not self.parent:
                    # Would be moved to next workspace- do nothing
                    return
                else:
                    # Container has escaped its immediate parallel parent
                    current = current.parent
                    if not current.parent:
                        # Escaped the workspace, not considered here
                        return
                    continue

            ancestor = current

        if target:
            # // Container will move in with its cousin
            # 		container_move_to_container_from_direction(container,
            # 				target, move_dir);
            # 		return true;
            return False
            raise NotImplementedError()  # TODO
        elif not wrapped and not self.parent.parent and len(self.parent.children) == 1:
            # Treat singleton children as if they are at workspace level like i3
            # 		# // https://github.com/i3/i3/blob/1d9160f2d247dbaa83fb62f02fd7041dec767fc2/src/move.c#L367
            # return container_move_to_next_output(container,
            # 				ancestor->pending.workspace->output, move_dir);
            return False
            raise NotImplementedError()  # TODO
        else:
            # Container will be promoted
            old_parent = self.parent
            if ancestor.parent:
                #  Container will move in with its parent
                self.detach()
                ancestor.parent.add_child(self, index + (0 if offs < 0 else 1) - 1)
            else:
                # Container will move to workspace level,
                # may be re-split by workspace_layout
                # workspace_insert_tiling(ancestor->pending.workspace, container,
                # 					index + (offs < 0 ? 0 : 1));
                self.detach()
                ancestor.root().add_child(self, index + (0 if offs < 0 else 1) - 1)

            if old_parent:
                old_parent.reap_empty()

            # workspace_squash
            # TODO
            return True

    def detach(self):
        if self.parent is not None:
            self.parent.children.remove(self)
            self.parent = None

    def get_node_by_con_id(self, con_id):
        """
        Get the node with the given con_id.

        :param con_id: The con_id to search for
        :return: The node with the given con_id
        """
        return next(node for node in self.nodes() if node.con_id == con_id)

    def has_ancestor(self, ancestor: 'Container') -> bool:
        """
        Returns True if the given ancestor is an ancestor of this container.
        """
        return ancestor in self.parents()

    def iter_bfs(self):
        """
        Iterate over all nodes in breadth-first order.
        """
        queue = [self]
        while queue:
            node = queue.pop(0)
            yield node
            # Skip split containers with a single child
            queue.extend(node.children)

    def iter_dfs(self):
        """
        Iterate over all nodes in depth-first order.
        """
        yield self
        for child in self.children:
            yield from child.iter_dfs()

    def replace(self, other: 'Container'):
        if self.parent is not None:
            self.add_sibling(other)
            self.detach()

    def nodes(self):
        """
        Generates all nodes.
        """
        yield from self.iter_dfs()

    def count_nodes(self):
        return sum(1 for _ in self.nodes())

    def count_relevant_nodes(self):
        return sum(1 for node in self.nodes() if not (isinstance(node, SplitContainer)
                                                      and len(node.children) == 1 and isinstance(node.children[0],
                                                                                                 SplitContainer)))

    def compare(self, other: 'LayoutNode') -> int:
        """
        Compare this layout to another layout. Returns a similarity score.
        This implementation is not sound.
        :param other: The other layout.
        :return: int: Matching nodes
        """
        score = 0

        queue = [(self, other, [], 1)]
        while queue:
            this, other, alternate_nodes, depth = queue.pop(0)

            while isinstance(this, SplitContainer) and len(this.children) == 1 and isinstance(this.children[0],
                                                                                              SplitContainer):
                this = this.children[0]

            while isinstance(other, SplitContainer) and len(other.children) == 1 and isinstance(other.children[0],
                                                                                                SplitContainer):
                other = other.children[0]

            if this == other:
                score += 1 / depth
            elif isinstance(this, SplitContainer) and not this.con_id and isinstance(other,
                                                                                     SplitContainer) and this.layout == other.layout:
                score += 1 / depth
            elif isinstance(this, SplitContainer) and isinstance(other, SplitContainer):
                score += 0.5 / depth
            elif other in alternate_nodes:
                score += 0.5 / depth
            else:
                score += 0.25 / depth

            if this != other:
                other.expected = this

            for i, child in enumerate(this.children):
                if i < len(other.children):
                    queue.append((child, other.children[i], this.children, depth + 1))

        return score

    @classmethod
    def from_json(cls, node, parent=None):

        if "layout" in node:
            con = SplitContainer(node["layout"], [], parent=parent, rect=node["rect"])
            for child in node["children"]:
                con.children.append(cls.from_json(child, parent=con))
        else:
            con = WindowContainer(node["swallows"], parent=parent, rect=node["rect"])

        return con

    def __hash__(self):
        return self.con_id if self.con_id else self.fake_id

    @classmethod
    def from_con(cls, con, parent=None):
        if con.layout == "none":
            # It is a leaf node
            # determine the matching criteria:
            swallows = {}
            if con.window_class is not None:
                swallows["class"] = con.window_class
            elif con.app_id is not None:
                swallows["app_id"] = con.app_id
            node = WindowContainer(swallows, con_id=con.id, parent=parent, rect={
                "width": con.rect.width,
                "height": con.rect.height,
                "percent": con.percent,
            })
        else:
            # It is a split container
            node = SplitContainer(con.layout, [], con_id=con.id, parent=parent, rect={
                "width": con.rect.width,
                "height": con.rect.height,
                "percent": con.percent,
            })
            for child in con.nodes:
                node.children.append(LayoutNode.from_con(child, parent=node))

        return node


class SplitContainer(LayoutNode):
    """
    A split container has a layout, and can have one or more children.
    """

    def __init__(self, layout, children, con_id=None, parent=None, fake_id=None, rect=None):
        super().__init__(children=children, con_id=con_id, parent=parent, fake_id=fake_id, rect=rect)
        self.layout = layout
        match layout:
            case "splitv":
                self.orientation = "vertical"
            case "splith":
                self.orientation = "horizontal"
            case "stacked":
                self.orientation = "vertical"
            case "tabbed":
                self.orientation = "horizontal"
            case _:
                raise ValueError("Unknown layout: {}".format(layout))

    def to_json(self):
        return {
            "layout": self.layout,
            "rect": self.rect,
            "children": [child.to_json() for child in self.children]
        }

    def workspace_wrap_children(self):
        middle: Container = SplitContainer(self.layout, [])
        for child in list(self.children):
            child.detach()
            middle.add_child(child)
        self.add_child(middle)
        return middle

    def reap_empty(self):
        # // clean-up, destroying parents if the container was the last child
        if len(self.children) == 0:
            if self.parent is not None:
                self.parent.reap_empty()
                self.detach()

    def flatten(self):
        if len(self.children) == 1:
            child = self.children[0]
            parent = self.parent
            self.replace(child)
            if parent:
                parent.flatten()

    def replace_child(self, old_child, new_child):
        """
        Replace a child with another child.
        :param old_child: The old child
        :param new_child: The new child
        """
        new_child.detach()
        for i, child in enumerate(self.children):
            if child == old_child:
                self.add_child(new_child, i)
                old_child.detach()

    def __eq__(self, other):
        if not isinstance(other, SplitContainer):
            return False
        if self.con_id and other.con_id:
            return self.con_id == other.con_id
        return self.layout == other.layout

    def __str__(self):
        s = ""
        match self.layout:
            case "splith":
                s += "Horizontal Split"
            case "splitv":
                s += "Vertical Split"
            case "tabbed":
                s += "Tabbed Split"
            case "stacked":
                s += "Stacked Split"
        if self.con_id:
            s += f" (con_id={self.con_id})"
        return s

    def __hash__(self):
        return self.con_id if self.con_id else self.fake_id

    def __repr__(self):
        if self.con_id:
            return f"SplitContainer(con_id={self.con_id}, layout={self.layout}, children={len(self.children)})"
        else:
            return f"SplitContainer(layout={self.layout}, children={len(self.children)})"


class WindowContainer(LayoutNode):
    """
    A window container has a swallow, and can have no children.
    """

    def __init__(self, swallows, con_id=None, parent=None, rect=None):
        super().__init__(con_id=con_id, parent=parent, rect=rect)
        self._swallows = swallows

    def swallows(self, other):
        if not isinstance(other, WindowContainer):
            return False

        if self.con_id:
            return other.con_id == self.con_id
        else:
            if "class" in self._swallows:
                # TODO: regex
                return self._swallows.get('class') == other._swallows.get('class')
            elif "app_id" in self._swallows:
                return self._swallows.get('app_id') == other._swallows.get('app_id')
            else:
                return False

    def name(self):
        if 'app_id' in self._swallows:
            return self._swallows['app_id']
        elif 'class' in self._swallows:
            return self._swallows['class']
        else:
            return None

    def to_json(self):
        return {
            "swallows": self._swallows,
            "rect": self.rect,
        }

    def __eq__(self, other):
        if isinstance(other, WindowContainer):
            if other.con_id and self.con_id:
                return other.con_id == self.con_id
            elif "class" in self._swallows and "class" in other._swallows:
                return self._swallows["class"] == other._swallows["class"]
            elif "app_id" in self._swallows and "app_id" in other._swallows:
                return self._swallows["app_id"] == other._swallows["app_id"]
        return False

    def __hash__(self):
        return self.con_id if self.con_id else self.fake_id

    def __repr__(self):
        if self.con_id:
            return f"WindowContainer(con_id={self.con_id}, swallows={self._swallows})"
        else:
            return f"WindowContainer(swallows={self._swallows})"

    def __str__(self):
        s = 'Swallows: ' if not self.con_id else 'Window: '
        match self._swallows:
            case {'app_id': app_id}:
                s += f"{app_id}"
            case {'class': class_name}:
                s += f"{class_name}"
            case _:
                s += f"Unknown Swallow"

        if self.con_id:
            s += f" (con_id={self.con_id})"
        # if self.rect:
        #     s += f" (rect={self.rect})"
        return s


Container = Union[LayoutNode, SplitContainer, WindowContainer]
