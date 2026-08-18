import time
from threading import Thread

from .counter import Counter
from .farmsync import Farmsync, FarmsyncError
from .output import Output
from .roblox import Roblox
from .thread_lock import lock
from .util import Util


def main() -> None:
    config = Util.config()
    if "REPLACE" in config["api_key"]:
        Output.error("Set 'api_key' in input/config.json before running.")
        return
    if "REPLACE" in config["farm_token"]:
        Output.error("Set 'farm_token' in input/config.json before running.")
        return

    threads = config["threads"]
    round_delay = config["round_delay"]
    farm = Farmsync(config["farm_token"])
    print(f"FarmsyncSolver  |  threads={threads}")
    round_n = 0

    try:
        while True:
            round_n += 1
            Output.banner(f"Round {round_n}")
            try:
                accounts = farm.solvable_accounts()
            except FarmsyncError as e:
                Output.error(f"farmsync.cloud unreachable: {e}")
                time.sleep(max(round_delay, 10))
                continue

            if not accounts:
                Output.info("no solvable accounts this round")
            else:
                Output.info(f"{len(accounts)} solvable, {threads} threads")
                counter = Counter()
                counts = {"joined": 0, "solved": 0, "fail": 0}
                workers = [Thread(target=Roblox(lock, counter, accounts, counts).check, daemon=True)
                           for _ in range(min(threads, len(accounts)))]
                for t in workers:
                    t.start()
                for t in workers:
                    t.join()
                Output.summary(counts)

            if round_delay <= 0:
                break
            time.sleep(round_delay)
    except KeyboardInterrupt:
        print("\nstopped.")
