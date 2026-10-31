"""Resolve scalar mapped LUT cones across actual instance ports, read-only."""
from functools import lru_cache
import re
from audit_cpu_ads import Cone, signal
from ads_bdd import lut_inputs


class HierCone:
    def __init__(self, source, root='CoreTop'):
        self.source = source
        self.modules = {m[1]: m[0] for m in re.finditer(r'(?ms)^module\s+(\w+).*?^endmodule', source)}
        assert root in self.modules
        self.root = root
        self.contexts = {(): (root, None, None)}
        self.pattern = re.compile(r'\b(' + '|'.join(map(re.escape, self.modules))
                                  + r')\s+(\\[^\s]+|\w+)\s*\((.*?)\);', re.S)
        self.hops = []

    @lru_cache(None)
    def directions(self, kind):
        header = self.modules[kind].split(');', 1)[0]
        return {signal(name): direction for direction, name in re.findall(
            r'\b(input|output|inout)\s+(?:\[[^\]]+\]\s+)?(\\[^\s,]+|\w+)', header)}

    @lru_cache(None)
    def children(self, context):
        kind = self.contexts[context][0]
        result = []
        for match in self.pattern.finditer(self.modules[kind]):
            child_kind, name, text = match.groups()
            name = signal(name)
            ports = {signal(port): signal(value) for port, value in re.findall(
                r'\.(\\[^\s(]+|\w+)\s*\(([^()]*)\)', text)}
            child = context + (name,)
            assert child not in self.contexts or self.contexts[child] == (child_kind, context, ports)
            self.contexts[child] = (child_kind, context, ports)
            result.append(child)
        return tuple(result)

    @lru_cache(None)
    def cone(self, kind):
        return Cone(self.source, kind)

    def find(self, kind):
        result = []
        def visit(context):
            current = self.contexts[context][0]
            if current == kind:
                result.append(context)
            else:
                for child in self.children(context):
                    visit(child)
        visit(())
        assert len(result) == 1, (kind, result)
        return result[0]

    def canonical(self, context, net, active=None):
        active = set() if active is None else active
        net = signal(net)
        key = (context, net)
        assert key not in active, 'Port/alias cycle ' + str(key)
        active.add(key)
        try:
            kind, parent, ports = self.contexts[context]
            c = self.cone(kind)
            if net in ("1'b0", "1'b1") or net in c.drivers:
                return key
            if net in c.aliases:
                return self.canonical(context, c.aliases[net], active)
            if self.directions(kind).get(net) in ('input', 'inout'):
                if parent is None:
                    return key
                assert net in ports, 'Unconnected input ' + str(key)
                target = (parent, ports[net])
            else:
                matches = []
                for child in self.children(context):
                    child_kind, _, bindings = self.contexts[child]
                    for port, value in bindings.items():
                        if value == net and self.directions(child_kind).get(port) == 'output':
                            matches.append((child, port))
                assert len(matches) == 1, ('Unknown/multiple scalar driver', key, matches)
                target = matches[0]
            self.hops.append((key, target))
            return self.canonical(*target, active=active)
        finally:
            active.remove(key)

    def expression(self, context, target, stops):
        anchors = {self.canonical(ctx, net): name for name, (ctx, net) in stops.items()}
        assert len(anchors) == len(stops), 'Aliased distinct stop variables'
        active = set()
        @lru_cache(None)
        def visit(ctx, net):
            key = self.canonical(ctx, net)
            if key in anchors:
                return ('var', anchors[key])
            ctx, net = key
            if net in ("1'b0", "1'b1"):
                return ('const', int(net[-1]))
            assert key not in active, 'Hierarchical combinational cycle ' + str(key)
            active.add(key)
            try:
                kind = self.contexts[ctx][0]
                c = self.cone(kind)
                assert net in c.drivers, 'Unknown non-stop input ' + str(key)
                node, port = c.drivers[net]
                assert port != 'Q', 'Unexpected sequential leaf ' + str(key)
                table, pins = lut_inputs(node, port)
                return ('lut', table, tuple(visit(ctx, pin) for pin in pins))
            finally:
                active.remove(key)
        expression = visit(context, target)
        def leaves(node):
            if node[0] == 'var':
                return {node[1]}
            if node[0] == 'const':
                return set()
            return set().union(*(leaves(pin) for pin in node[2]))
        return expression, leaves(expression)

    @staticmethod
    def evaluate(expression, values):
        kind = expression[0]
        if kind == 'var':
            return values[expression[1]]
        if kind == 'const':
            return expression[1]
        index = sum(HierCone.evaluate(pin, values) << i for i, pin in enumerate(expression[2]))
        return (expression[1] >> index) & 1
