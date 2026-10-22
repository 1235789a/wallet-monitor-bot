import unittest
from first_principles_pilot import route, pilot_report


def row(name, channel, stage="READY_FOR_MANUAL_OUTREACH"):
    domain=name.lower().replace(" ", "")+".example"
    unique=sum((i+1)*ord(c) for i,c in enumerate(name))%10_000_000
    link=(f"https://wa.me/91999{unique:07d}" if channel=="whatsapp" else "https://t.me/human_"+name.lower())
    return {"company":name,"website":"https://"+domain,
            "source":{"url":"https://clutch.co/company/"+name.lower()},
            "contact":{"official_page":"https://"+domain+"/contact"},
            "chat_url":link,"stage":stage,"gate_reasons":["PURCHASE_FIT_UNKNOWN"] if stage!="READY_FOR_MANUAL_OUTREACH" else []}


class PilotTests(unittest.TestCase):
    def test_routes(self):
        self.assertEqual(route('https://wa.me/message/B67I2UMAEELQH1'), 'whatsapp')
        self.assertEqual(route('https://api.whatsapp.com/send/?phone=919999999999'), 'whatsapp')
        self.assertEqual(route('https://t.me/nadiia_generis'), 'telegram')
        self.assertIsNone(route('https://t.me/sales_support_bot'))
        self.assertIsNone(route('https://wa.me/not-phone'))
    def test_quotas_and_dedupe(self):
        a=[row('WA'+str(i),'whatsapp') for i in range(12)]+[row('TG'+str(i),'telegram') for i in range(3)]
        a += [row('WA0','whatsapp')]
        result=pilot_report({'rows':a})
        self.assertEqual(result['ready_count'],{'whatsapp':10,'telegram':2})
        self.assertEqual(result['gaps'],{'whatsapp':0,'telegram':0})
        self.assertEqual(len(result['ready']),12)
    def test_two_brands_shared_whatsapp_are_not_two_leads(self):
        a=row('One','whatsapp')
        b=row('Two','whatsapp')
        b['chat_url']=a['chat_url']
        result=pilot_report({'rows':[a,b]})
        self.assertEqual(result['ready_count']['whatsapp'], 1)
        self.assertIn('DUPLICATE_OR_MISSING_ID',[x['state'] for x in result['review']])
    def test_unknown_buyer_stays_hold(self):
        data=pilot_report({'rows':[row('Example','whatsapp',stage='HOLD')]})
        self.assertEqual(data['gaps']['whatsapp'],10)
        self.assertEqual(data['review'][0]['state'],'EVIDENCE_HOLD')
    def test_source_and_official_gate(self):
        a=row('NoSource','telegram')
        a['source']['url']=a['website']+'/about'
        self.assertEqual(pilot_report({'rows':[a]})['review'][0]['state'],'SOURCE_OR_ROUTE_HOLD')
        b=row('Wrong','whatsapp')
        b['contact']['official_page']='https://third-party.example'
        self.assertEqual(pilot_report({'rows':[b]})['review'][0]['state'],'SOURCE_OR_ROUTE_HOLD')

if __name__=='__main__': unittest.main()
