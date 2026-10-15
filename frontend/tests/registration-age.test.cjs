const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'), Module=require('node:module'), ts=require('typescript'), React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
function load(file,imports={}){const filename=path.resolve(file),m=new Module(filename,module);m.paths=Module._nodeModulePaths(path.dirname(filename));const req=m.require.bind(m);m.require=name=>imports[name]??req(name);m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,filename);return m.exports;}
const ages=load('src/lib/registration-age.ts');
test('age selection has no default eligibility and applies 13/18 boundaries exactly',()=>{
 for(const value of ['', '-1','12.5','NaN','121','18x'])assert.equal(ages.ageBand(value),null);
 for(const value of ['0','12'])assert.equal(ages.ageBand(value),'under_13');
 for(const value of ['13','17'])assert.equal(ages.ageBand(value),'13_to_17');
 for(const value of ['18','80','120'])assert.equal(ages.ageBand(value),'18_or_over');
 assert.equal(ages.ageLabel(''),'Выберите возраст');assert.equal(ages.ageLabel('18'),'18 лет');assert.equal(ages.ageLabel('21'),'21 год');assert.equal(ages.ageLabel('22'),'22 года');
});
test('age form submits only the age band after deliberate confirmation',async()=>{
 let cursor=0, submitted, eligible;
 const values=['18',true,false,'',false,''];
 const hooks={...React,useState:init=>[values[cursor++]??init,()=>{}]};
 const {AgeScreen}=load('src/components/age-screen.tsx',{react:hooks,'../lib/registration-age':ages,'./guardian-request':{GuardianRequest:()=>null},'../lib/platform':{platformRequest:async(path,body)=>{submitted={path,body};return{eligible:true,age_check_token:'proof'};}}});
 // Component uses useId from React; render with actual dispatcher to exercise the submit handler.
 const Base=React.createElement(()=>{cursor=0;const form=AgeScreen({onEligible:token=>{eligible=token;}});submitted=form;return null;});render(Base);
 const handler=submitted.props.onSubmit;
 await handler({preventDefault(){}});
 assert.deepEqual(submitted,{path:'/api/accounts/age-check',body:{age_band:'18_or_over'}});assert.equal(eligible,'proof');
 assert.doesNotMatch(JSON.stringify(submitted),/birth|email|password|"18"/);
});
for (const [age,guardianEnabled] of [['13',false],['12',false],['13',true]]) {
 test(`age ${age} can be corrected to 21 with a fresh confirmation (guardian enabled: ${guardianEnabled})`,async()=>{
  const values=[],requests=[];let cursor=0,tree,eligible;
  const hooks={...React,useState:init=>{const index=cursor++;if(!(index in values))values[index]=init;return[values[index],value=>{values[index]=value;}];}};
  const {AgeScreen}=load('src/components/age-screen.tsx',{react:hooks,'../lib/registration-age':ages,'./guardian-request':{GuardianRequest:()=>React.createElement('p',null,'Guardian request')},'../lib/platform':{platformRequest:async(path,body)=>{requests.push(body);return{eligible:body.age_band==='18_or_over',next_step:body.age_band==='13_to_17'?'guardian':'blocked',age_check_token:body.age_band==='18_or_over'?'adult-proof':'minor-proof'};}}});
  const view=()=>render(React.createElement(()=>{cursor=0;tree=AgeScreen({guardianEnabled,onEligible:token=>{eligible=token;}});return tree;}));
  const find=(node,predicate)=>{if(!React.isValidElement(node))return; if(predicate(node))return node;for(const child of React.Children.toArray(node.props.children)){const match=find(child,predicate);if(match)return match;}};
  const input=type=>find(tree,node=>node.type==='input'&&node.props.type===type);
  view();input('number').props.onChange({target:{value:age}});
  view();input('checkbox').props.onChange({target:{checked:true}});
  view();await tree.props.onSubmit({preventDefault(){}});
  const result=view();assert.equal(eligible,undefined);
  if(guardianEnabled)tree.props.onCorrectAge();
  else {assert.match(result,/Исправить возраст/);find(tree,node=>typeof node.props.onCorrect==='function').props.onCorrect();}
  view();assert.equal(input('checkbox').props.checked,false);
  input('number').props.onChange({target:{value:'21'}});
  view();assert.equal(input('checkbox').props.checked,false);
  assert.equal(find(tree,node=>node.type==='button'&&node.props.type==='submit').props.disabled,true);
  await tree.props.onSubmit({preventDefault(){}});assert.equal(requests.length,1);
  input('checkbox').props.onChange({target:{checked:true}});
  view();await tree.props.onSubmit({preventDefault(){}});
  assert.deepEqual(requests,[{age_band:age==='13'?'13_to_17':'under_13'},{age_band:'18_or_over'}]);
  assert.equal(eligible,'adult-proof');
 });
}
test('a late parent approval cannot override an age correction after leaving the consent screen',async()=>{
 const effects=[];let resolve,eligible;
 const hooks={...React,useEffect:effect=>effects.push(effect),useCallback:callback=>callback};
 const {GuardianRequest}=load('src/components/guardian-request.tsx',{react:hooks,'../lib/platform':{platformRequest:()=>new Promise(done=>{resolve=done;})}});
 render(React.createElement(GuardianRequest,{ageToken:'old-minor-proof',onEligible:token=>{eligible=token;},onCorrectAge:()=>{}}));
 const cleanups=effects.map(effect=>effect());
 for(const cleanup of cleanups)if(typeof cleanup==='function')cleanup();
 resolve({status:'approved'});await Promise.resolve();
 assert.equal(eligible,undefined);
});
test('parent confirmation page does not precheck consent or submit on load',()=>{
 let calls=0;
 const {GuardianConsent}=load('src/components/guardian-consent.tsx',{'../lib/platform':{platformRequest:()=>{calls++;}},'./auth-study':{AuthStudy:()=>null},'./forma-mark':{FormaMark:()=>null}});
 const html=render(React.createElement(GuardianConsent));
 assert.match(html,/Открываем запрос/);assert.doesNotMatch(html,/checked=""/);assert.equal(calls,0);
 const nav=load('src/lib/navigation.ts');assert.equal(nav.publicPath('/guardian-consent'),true);assert.equal(nav.publicPath('/api/accounts/guardian-consent/request'),false);
});
