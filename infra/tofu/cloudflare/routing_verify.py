"""Read-only publisher admission checks; missing live identities remain incomplete."""

import argparse
from copy import deepcopy
import hashlib
import json
import re
import urllib.error
import urllib.request

import yaml

import operations as op
from backend import NoRedirect
from control_plane import require
from probes import access_denied, request, run_live
from receipt import normalize


def receipt():
    value = json.loads((op.ROOT / '.artifacts/cloudflare/plan.json').read_text())
    normalize(op.ROOT, value)
    require(value.get('routing_enabled') is True, 'publisher routing has not been applied')
    audiences = value.get('publisher_access_audiences', [])
    require(len(audiences) == len(set(audiences)) == 2
            and all(re.fullmatch('[a-f0-9]{64}', item) for item in audiences), 'invalid live Access audiences')
    require(re.fullmatch('[a-z0-9-]+', value.get('access_team_name', '')), 'invalid live Access organization')
    return value


def probes(manifest, inputs):
    publisher = deepcopy(manifest)
    publisher['routes'] = [r for r in publisher['routes'] if r['id'] == 'publisher-admin-api']
    require(len(publisher['routes']) == 1, 'missing publisher route')
    route = publisher['routes'][0]
    route['status'] = 'adopted'
    outcomes = run_live(publisher, inputs)[route['id']]
    # Service Auth must not act as a UI or arbitrary-path exception.
    headers = {'CF-Access-Client-Id': inputs.get('N8N_ACCESS_CLIENT_ID', 'invalid-disposable-probe'),
               'CF-Access-Client-Secret': inputs.get('N8N_ACCESS_CLIENT_SECRET', 'invalid-disposable-probe')}
    for path, kind in (('/', 'service-token-at-ui'), ('/__disposable-invalid-path-probe', 'service-token-outside-api')):
        require(access_denied(request(route['hostname'], path, headers)), 'service token escapes its API path')
        outcomes[kind] = 'denied'
    for bucket in ('dholbeat-core-backups', 'dholbeat-publisher-backups'):
        response = request(op.ACCOUNT + '.r2.cloudflarestorage.com', '/' + bucket + '/__disposable-private-object')
        require(response.status == 403, 'backup bucket anonymous read denial was not proven')
        outcomes[bucket + '-anonymous'] = 'denied'
    return outcomes


def media_probe(inputs):
    path, expected = inputs.get('MEDIA_PROBE_PATH'), inputs.get('MEDIA_PROBE_SHA256')
    if not path or not expected:
        return 'reviewed-media-fixture-required'
    require(re.fullmatch('/wp06b-fixture/[a-z0-9-]{1,64}', path)
            and re.fullmatch('[a-f0-9]{64}', expected), 'invalid media fixture coordinates')
    http = urllib.request.Request('https://media.chayan.me' + path, method='GET')
    try:
        response = urllib.request.build_opener(NoRedirect).open(http, timeout=15)
    except urllib.error.HTTPError:
        raise op.OperationError('public media fixture delivery failed') from None
    with response:
        data = response.read(1024 * 1024 + 1)
        require(response.status == 200 and len(data) <= 1024 * 1024
                and hashlib.sha256(data).hexdigest() == expected, 'media bytes differ from reviewed fixture')
    return 'accepted'


def verify(inputs):
    # Native provider refresh proves every guarded selector, including lifecycle
    # and disabled r2.dev endpoints. It also protects all prior adopted objects.
    op.plan(inputs)
    bound = receipt()
    manifest = op.documents()[0]
    api = op.Cloudflare(inputs['CLOUDFLARE_API_TOKEN'])
    for bucket in ('dholbeat-core-backups', 'dholbeat-publisher-backups'):
        result = api.request('GET', f'/accounts/{op.ACCOUNT}/r2/buckets/{bucket}/domains/custom')
        require(isinstance(result, dict) and result.get('domains') == [], 'backup bucket has an unknown or custom public domain')
    outcomes = probes(manifest, inputs)
    outcomes['public-media-fixture'] = media_probe(inputs)
    complete = all(value in {'accepted', 'denied'} for value in outcomes.values())
    op.evidence('routing-verify', {'provider_mutations': 0, 'complete': complete,
        'inputs_sha256': bound['inputs_sha256'], 'results': outcomes,
        'media_expiry_policy_seconds': 604800, 'observed_media_expiry': 'seven-day-canary-required'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt-only', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(receipt(), sort_keys=True))
