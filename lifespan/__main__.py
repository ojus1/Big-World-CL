import argparse
import runpy
import sys
from .agents import POLICIES
from .experiment import demo


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("integrated", "personas", "ecosystem"):
        command = sys.argv.pop(1)
        module = "lifespan." + ("ecosystem_run" if command == "ecosystem" else command)
        runpy.run_module(module, run_name="__main__")
        return
    parser = argparse.ArgumentParser(description="Generate evolving enterprises and persistent employee–agent lifespans.")
    parser.add_argument("command", choices=["ecosystem", "integrated", "personas", "demo"],
                        help="ecosystem: persistent MiroFish/Persona/Hermes world; integrated: earlier single-enterprise run; personas: import data; demo: archived rule-controller fixture")
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--days", type=int, default=84)
    parser.add_argument("--enterprises", type=int, default=3)
    parser.add_argument("--policies", nargs="+", choices=POLICIES, default=list(POLICIES))
    parser.add_argument("--no-drift", action="store_true")
    args = parser.parse_args()
    print(demo(args.out, args.seed, args.days, args.enterprises, args.policies, not args.no_drift))


if __name__ == "__main__":
    main()
