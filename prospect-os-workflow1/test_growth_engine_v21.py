import unittest,copy
from prospect_os.growth_engine_v21 import qualify,allocate,permit_content,canonical_chat,source_yield
def ev(url='https://evidence.example.org/item',claim='Reviewed public business evidence'):
 return dict(url=url,claim=claim,grade='WEB_OBSERVED',evidence_id='E1',retrieved_at='2026-10-21T10:00:00+08:00')
def dossier():
 return dict(industry_id='charter-cpt',score=8.8,critical_facts_verified=True,review_status='PASS',sources=[dict(ev('https://source%d.example.org/item'%i),source_type='directory' if i==0 else 'operator') for i in range(4)])
def row():
 return dict(entity_id='new1',company='New Charter',website='https://newcharter.example.com',chat_url='https://wa.me/27721234567',industry_id='charter-cpt',history_coverage_reviewed=True,
 source=dict(ev(),source_id='DIR',record_id='42',snapshot_hash='abc'),website_evidence=ev(),contact=dict(channel='whatsapp',route_type='BUSINESS_HUMAN',attribution_verified=True,evidence=ev()),
 icp_review='PASS',icp_evidence=ev(),purchase_fit=dict(review='PASS',evidence=ev(),internal_capacity_reviewed=True),client_context_id='C1',
 business_class_verified='private_charter',business_class_claimed='private_charter',final_copy="Hi New Charter team, I'm with MultiHub. I check how private charters appear when visitors ask ChatGPT for a sunset cruise. Would a short example help?",
 outreach_qa=dict(status='PASS',blind_review_pass=True,facts_reviewed=True),contact_status='NOT_SENT')
class Gates(unittest.TestCase):
 def assess(self,r):return qualify(r,[],dossier())
 def test_positive_presence_does_not_disqualify(self):
  r=row();r['ai_tests']=[{'brand_present':True}];self.assertEqual(self.assess(r)['stage'],'READY_FOR_MANUAL_OUTREACH')
 def test_cross_batch_prior_not_new(self):
  r=row();old=copy.deepcopy(r);old['contact_status']='UNKNOWN';self.assertIn('PRIOR_BATCH_REVIEW',qualify(r,[old],dossier())['gate_reasons'])
 def test_same_phone_different_brand(self):
  r=row();old=dict(company='Other Brand',chat_url=r['chat_url'],contact_status='DECLINED');self.assertIn('HISTORY_CONTACTED_EXCLUDE',qualify(r,[old],dossier())['gate_reasons'])
 def test_tg_channel_and_bot(self):
  for u in ['https://t.me/example_bot','https://t.me/+invite','https://t.me/business_channel']:
   r=row();r['chat_url']=u;r['contact']['route_type']='CHANNEL';self.assertIn('CONTACT_NOT_DIRECT_HUMAN',self.assess(r)['gate_reasons'])
 def test_fake_wa_and_phone_only(self):
  for u in ['https://wa.me/123','https://wa.me/jake_jones','tel:+27721234567']:
   self.assertIsNone(canonical_chat(u))
  r=row();r['contact']['attribution_verified']=False;self.assertEqual(self.assess(r)['stage'],'HOLD')
 def test_marketing_internal_capacity(self):
  r=row();r['internal_diy_confirmed']=True;self.assertIn('PARTNER_OR_DIY',self.assess(r)['gate_reasons'])
 def test_old_80_claim_cannot_override_source(self):
  r=row();r['stage']='READY_FOR_MANUAL_OUTREACH';r['claimed_qualified']=80;r['source']['record_id']='';self.assertEqual(self.assess(r)['stage'],'HOLD')
 def test_untested_negative_claim(self):
  r=row();r['final_copy']='We found a gap: your competitors appear. Want proof?';self.assertIn('UNTESTED_NEGATIVE_CLAIM',self.assess(r)['gate_reasons'])
 def test_home_in_rio_misread(self):
  r=row();r.update(business_class_verified='holiday_rental',business_class_claimed='real_estate_sales');self.assertIn('INDUSTRY_MISREAD',self.assess(r)['gate_reasons'])
 def test_link_without_copy(self):
  r=row();r['final_copy']='';self.assertIn('COPY_NOT_USABLE',self.assess(r)['gate_reasons'])
 def test_free_check_not_public_permission(self):
  self.assertFalse(permit_content(dict(scope='PRIVATE',free_check=True),public=True))
 def test_regulated_stays_isolated(self):
  r=row();r['regulated']=True;r['compliance_review']='PASS';self.assertIn('HOLD_REGULATED',self.assess(r)['gate_reasons'])
 def test_industry_gate_cannot_self_score_without_sources(self):
  d=dossier();d['sources']=[];self.assertIn('INDUSTRY_RESEARCH_PENDING',qualify(row(),[],d)['gate_reasons'])
 def test_unknown_fit_not_high_score(self):
  r=row();r['purchase_fit']['review']='UNKNOWN';r['claimed_score']=10;self.assertEqual(self.assess(r)['stage'],'HOLD')
 def test_release_second_dedup_and_exact_gaps(self):
  a=self.assess(row());b=copy.deepcopy(a);b.update(entity_id='new2',company='alias');res=allocate([a,b]);self.assertEqual(len(res['rows']),1);self.assertEqual(res['gaps'],{'whatsapp':63,'telegram':16})
 def test_zero_ready_cost_unknown(self):
  r=source_yield([{'entity_id':str(i),'stage':'HOLD'} for i in range(30)],elapsed_seconds=600)
  self.assertIsNone(r['research_minutes_per_ready']);self.assertEqual(r['action'],'PAUSE_EXPANSION_REVIEW_SOURCE')
if __name__=='__main__':unittest.main()
