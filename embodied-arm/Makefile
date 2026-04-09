.PHONY: verify package

verify:
	python scripts/verify_third_party_governance.py
	bash scripts/verify_split_repository.sh

package:
	python scripts/package_split_release.py
