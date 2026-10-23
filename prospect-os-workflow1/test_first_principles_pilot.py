import unittest
from first_principles_pilot import route, pilot_report, outbound_history_verified


PROOF = {"review_status":"PASS","reviewer":"human-review",
         "private_evidence_ref":"private://wa-tg-export-20261023",
         "covers_sent_through":"2026-10-23T12:00:00+00:00",
         "channels":{"whatsapp":{"reviewed":True,"source_id":"wa-export"},
                     "telegram":{"reviewed":True,"source_id":"tg-export"}}}
BATCH_START = "2026-10-23T10:00:00+00:00"


def audited(rows, proof=PROOF):
    return {"rows":rows,"outbound_history_proof":proof,"batch_started_at":BATCH_START}





def row(name, channel, stage="READY_FOR_MANUAL_OUTREACH"):
    domain=name.lower().replace(" ", "")+".example"
    unique=sum((i+1)*ord(c) for i,c in enumerate(name))%10_000_000
    link=(f"https://wa.me/91999{unique:07d}" if channel=="whatsapp" else "https://t.me/human_"+name.lower())
    return {"company":name,"website":"https://"+domain,
            "source":{"url":"https://clutch.co/company/"+name.lower()},
            "contact":{"official_page":"https://"+domain+"/contact"},
            "chat_url":link,"stage":stage,"gate_reasons":["PURCHASE_FIT_UNKNOWN"] if stage!="READY_FOR_MANUAL_OUTREACH" else []}


class PilotTests(unittest.TestCase):
    def test_fails_closed_without_current_outbound_history(self):
        result=pilot_report({"rows":[row("Unlogged","whatsapp")]})
        self.assertEqual(len(result["ready"]), 0)
        self.assertEqual(result["review"][0]["state"],"OUTBOUND_HISTORY_UNVERIFIED")
    def test_partial_or_stale_history_never_unlocks(self):
        self.assertFalse(outbound_history_verified({"review_status":"PASS",
                                                    "channels":{"whatsapp":{"reviewed":True,"source_id":"x"}}}, BATCH_START))
        stale=dict(PROOF, covers_sent_through="2026-10-22T12:00:00+00:00")
        self.assertFalse(outbound_history_verified(stale, BATCH_START))
    def test_routes(self):
        self.assertEqual(route('https://wa.me/message/B67I2UMAEELQH1'), 'whatsapp')
        self.assertEqual(route('https://api.whatsapp.com/send/?phone=919999999999'), 'whatsapp')
        self.assertEqual(route('https://t.me/nadiia_generis'), 'telegram')
        self.assertIsNone(route('https://t.me/sales_support_bot'))
        self.assertIsNone(route('https://wa.me/not-phone'))
    def test_quotas_and_dedupe(self):
        a=[row('WA'+str(i),'whatsapp') for i in range(12)]+[row('TG'+str(i),'telegram') for i in range(3)]
        a += [row('WA0','whatsapp')]
        result=pilot_report(audited(a))
        self.assertEqual(result['ready_count'],{'whatsapp':10,'telegram':2})
        self.assertEqual(result['gaps'],{'whatsapp':0,'telegram':0})
        self.assertEqual(len(result['ready']),12)
    def test_two_brands_shared_whatsapp_are_not_two_leads(self):
        a=row('One','whatsapp')
        b=row('Two','whatsapp')
        b['chat_url']=a['chat_url']
        result=pilot_report(audited([a,b]))
        self.assertEqual(result['ready_count']['whatsapp'], 1)
        self.assertIn('DUPLICATE_OR_MISSING_ID',[x['state'] for x in result['review']])
    def test_unknown_buyer_stays_hold(self):
        data=pilot_report(audited([row('Example','whatsapp',stage='HOLD')]))
        self.assertEqual(data['gaps']['whatsapp'],10)
        self.assertEqual(data['review'][0]['state'],'EVIDENCE_HOLD')
    def test_source_and_official_gate(self):
        a=row('NoSource','telegram')
        a['source']['url']=a['website']+'/about'
        self.assertEqual(pilot_report(audited([a]))['review'][0]['state'],'SOURCE_OR_ROUTE_HOLD')
        b=row('Wrong','whatsapp')
        b['contact']['official_page']='https://third-party.example'
        self.assertEqual(pilot_report(audited([b]))['review'][0]['state'],'SOURCE_OR_ROUTE_HOLD')

if __name__=='__main__': unittest.main()
