"""Whether three rolled lines meet every rule of a potential spec."""


def compile_matcher(spec):
    """Each rule is a minimum total across the three lines."""
    minimums = [rule["value"] for rule in spec["rules"]]

    def accepted(lines):
        totals = [sum(line[i] for line in lines) for i in range(len(minimums))]
        return all(total + 1e-10 >= minimum for total, minimum in zip(totals, minimums, strict=True))

    return accepted
