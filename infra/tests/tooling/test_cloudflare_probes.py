"""Route admission probes are adversarial, including failure of a down origin as evidence."""
import importlib.util
from pathlib import Path
import sys

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "tofu/cloudflare"
sys.path.insert(0, str(PACKAGE))
from probes import Response, check, matrix, verify_founder_policy
from edge import documents
from control_plane import ContractError

LOGIN = 'https://dholbeat.cloudflareaccess.com/cdn-cgi/access/login/team.chayan.me'


@pytest.mark.parametrize('kind', ['unauthenticated','wrong-founder','wrong-service-token','direct-ip','alternate-dns'])
@pytest.mark.parametrize('response', [Response(302, LOGIN), Response(403)])
def test_negative_auth_probe_requires_denial(kind, response):
    check(kind, response)


@pytest.mark.parametrize('response', [Response(200), Response(502), Response(503), Response(302, '/login'),
                                      Response(302, 'https://cloudflareaccess.com.evil.invalid/cdn-cgi/access/login')])
def test_origin_error_or_application_login_is_not_access_denial(response):
    with pytest.raises(ContractError): check('unauthenticated', response)


@pytest.mark.parametrize('kind,response', [('founder', Response(200)),('service-token',Response(200)),
    ('method',Response(405)),('path',Response(404)),('webhook-token',Response(401))])
def test_positive_and_scoped_machine_contracts(kind,response):
    check(kind,response)


@pytest.mark.parametrize('kind', ['founder','service-token','method','path','webhook-token'])
def test_denied_positive_or_exposed_machine_is_rejected(kind):
    response = Response(302, LOGIN) if kind in {'founder','service-token'} else Response(200)
    with pytest.raises(ContractError): check(kind,response)


def test_all_declared_routes_have_full_probe_matrix():
    cases = matrix(documents()[0])
    assert set(cases) == {'paperclip-admin','n8n-admin','approval-webhooks','publisher-admin-api'}
    assert {'founder','wrong-founder','unauthenticated','direct-ip','alternate-dns'} <= set(cases['paperclip-admin'])
    assert {'method','path','webhook-token'} <= set(cases['approval-webhooks'])
    assert {'service-token','wrong-service-token','path'} <= set(cases['publisher-admin-api'])


def test_missing_or_bypass_access_policy_fails():
    policy={'id':'founder', 'decision':'allow','include':[{'email':{'email':'mail@chayan.me'}}],'exclude':[],'require':[]}
    app={'domain':'team.chayan.me','type':'self_hosted','policies':[{'id':'founder'}],'options_preflight_bypass':False}
    verify_founder_policy(app,policy,'team.chayan.me')
    for changed in [{**app,'policies':[]},{**app,'options_preflight_bypass':True}]:
        with pytest.raises(ContractError): verify_founder_policy(changed,policy,'team.chayan.me')
    with pytest.raises(ContractError): verify_founder_policy(app,{**policy,'decision':'bypass'},'team.chayan.me')
