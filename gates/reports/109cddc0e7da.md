<!-- proofmark-ship head=109cddc0e7dafc0e4637d920603581404c945784 -->
# Report - OCP-CE-HR-Policy-Searcher, ocp/main..HEAD

## What shipped
- 109cddc docs: replace stale counts in README and CLAUDE.md with dated or live values

4 files changed, 68 insertions(+), 25 deletions(-)

## Test floor
2699 -> 2702  (ratcheted)

## Coverage (reported fact, never a gate)
TOTAL 11251 1349 88%  measured 2026-09-08T22:50:46+00:00

## What the gates did
passes 1, bound 1, blocks 0, overrides 0, exceptions 0

## Rollback
    git revert --no-edit 779a5a0c829b..HEAD
    # then restore gates/min_test_count.txt to 2699; the floor does not fall on its own

## To be written by a person - the tool cannot know these
- What you found and did NOT fix: README's Geographic Coverage table still lists specific institution and Land counts per row ("EU (22 institutions + member states)", "Germany (federal + 8 Länder)") that I did not re-measure; they are descriptive rather than the headline counts the chip named, and checking each against config/domains/ is its own pass. The guard only covers TEST counts; domain and tool counts are dated by hand and can go stale again, by design - a regex that refused every number in a README would refuse the README.
- The diagnosis you got wrong first, and what corrected it: The chip said HOW_IT_WORKS reports "24 sources" and README says "23 structured legislation APIs". Neither phrase exists in the files: HOW_IT_WORKS's "402 sources" is the domain count of the 1 September scan, README's "23" is a JSON sample in the API docs, and SOURCE_REGISTRY has 24 structured sources. So there was no stale structured-source claim to fix, and the domain headline was the real drift (four different figures, 360+ to 381, against 402 measured). Second: I expected the keyword claims (7 categories, 20 languages) to be stale too; config/keywords.yaml says they are exactly right.
- Numbered open questions: 1. Should the domain and country counts in README be generated (a tiny script writing the headline line from config/) rather than dated by hand? 2. Is "36 countries and the EU" the count the project wants to advertise, or should US states and Länder count toward the headline as they seem to have before ("40+")?
- Verified live by fetching real content (not a status code)? what, and what did it say: Yes. Counts came from running the code, not reading docs: ConfigLoader.get_enabled_domains("all") = 402; jurisdiction registry over their region slugs = 36 country-kind + 1 supranational + 28 us_state + 24 subnational + 12 group; len(SOURCE_REGISTRY) = 24; keywords.yaml = 7 categories with terms, 20 language keys; server.py = 12 Tool( entries; ls config/domains = 33 files + us/ 51; frontend suite 547/42 from the #51 run; gates/min_test_count.txt = 2699. The guard test: 2 failed on the stashed old docs, 3 passed on the new.
