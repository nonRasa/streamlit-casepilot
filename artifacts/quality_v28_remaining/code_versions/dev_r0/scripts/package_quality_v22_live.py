"""Create a new complete submission after live review, preserving older ZIPs."""
import hashlib
import json
import zipfile
from pathlib import Path
import package_submission as packaging
import verify_package
import verify_quality_v22_live_results


def main():
    root = packaging.ROOT
    folder = root / 'artifacts/quality_v22/live_comparison_01'
    if not verify_quality_v22_live_results.main():
        raise SystemExit('توقف: ممیزی نتیجهٔ واقعی عبور نکرد.')
    if not verify_package.main(folder / 'package_verification.json'):
        raise SystemExit('توقف: بررسی بسته عبور نکرد.')
    prior = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.zip')}
    packaging.ARCHIVE = 'streamlit-casepilot_quality_v22_live_submission.zip'
    packaging.MANIFEST = 'quality_v22_live_submission_manifest.json'
    packaging.main()
    archive = root / packaging.ARCHIVE
    manifest = json.loads((root / packaging.MANIFEST).read_text(encoding='utf-8'))
    with zipfile.ZipFile(archive) as z:
        matched = all(hashlib.sha256(z.read('streamlit-casepilot/' + name)).hexdigest() == digest
                      for name, digest in manifest['files'].items())
        seal = {'archive': archive.name, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'bytes': archive.stat().st_size, 'entries': len(z.namelist()),
                'crc_passed': z.testzip() is None, 'manifest_hashes_match': matched,
                'prior_archives_unchanged': all(hashlib.sha256((root / n).read_bytes()).hexdigest() == h for n, h in prior.items()),
                'secret_scan_passed_during_packaging': True}
    (folder / 'package_seal.json').write_text(json.dumps(seal, indent=2) + '\n', encoding='utf-8')
    if not all(seal[k] for k in ('crc_passed', 'manifest_hashes_match', 'prior_archives_unchanged')):
        raise SystemExit('توقف: کنترل نهایی بسته عبور نکرد.')
    print(json.dumps(seal))


if __name__ == '__main__':
    main()
