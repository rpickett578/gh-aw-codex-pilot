// Credential-free Linux contract test: pinned native MCP handler and native bundle
// import helper, real Git checkouts, preserved candidate. NO GitHub API publication.
const assert = require('node:assert/strict');
const cp = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const https = require('node:https');
const ROOT = path.resolve(__dirname, '..');
const PIN = '0627fdbe4beb5f3b71aa569f8d97150b87f2111a';
const BASE = 'b876867631bc89c7b5775c98c72f1b44a16c963f';
const LOCAL = 'phase2-reverse-ascii-v1';
const REMOTE = 'codex/' + LOCAL;
const SOURCE = 'src/reverse-ascii.mjs';
if (process.platform !== 'linux') throw new Error('Run unmodified native /tmp/gh-aw contract in hosted Linux CI');
const native = path.resolve(process.env.GH_AW_NATIVE_ACTIONS || '');
assert.equal(cp.execFileSync('git', ['-C', native, 'rev-parse', 'HEAD'], {encoding:'utf8'}).trim(), PIN);
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'pilot-native-publication-'));
assert.equal(path.dirname(temporary), path.resolve(os.tmpdir()));
// Never expose repository/runner credentials to the native Git/MCP subprocesses.
for (const key of Object.keys(process.env)) {
  if (/TOKEN|SECRET|PASSWORD|API_KEY|ACTIONS_ID_TOKEN|AUTHORIZATION/.test(key)) delete process.env[key];
}
Object.assign(process.env, {GIT_CONFIG_GLOBAL:path.join(temporary,'gitconfig'),GIT_CONFIG_NOSYSTEM:'1',
  GIT_ALLOW_PROTOCOL:'file',GIT_TERMINAL_PROMPT:'0',GITHUB_REPOSITORY:'rpickett578/gh-aw-codex-pilot',
  GITHUB_EVENT_NAME:'workflow_dispatch',DEFAULT_BRANCH:'main',GITHUB_SHA:BASE,RUNNER_TEMP:temporary,
  GITHUB_RUN_ID:'no-ai-contract',GITHUB_WORKFLOW_SHA:BASE});
fs.writeFileSync(process.env.GIT_CONFIG_GLOBAL, '');
const deny = () => { throw new Error('Network forbidden in no-AI native contract'); };
http.request = http.get = https.request = https.get = deny; global.fetch = deny;
function git(cwd, args, allowFailure=false) {
  const r=cp.spawnSync('git',args,{cwd,encoding:'utf8',env:process.env});
  if (r.error) throw r.error;
  if (!allowFailure && r.status!==0) throw new Error(`git ${args.join(' ')}: ${r.stderr}`);
  return r;
}
function python(cwd, args) {
  const r=cp.spawnSync('python3',args,{cwd,encoding:'utf8',env:process.env});
  assert.equal(r.status,0,r.stdout+r.stderr); return r.stdout;
}
function clone(name) {
  const directory=path.join(temporary,name);
  git(temporary,['clone','--quiet',origin,directory]);
  git(directory,['config','user.name','No-AI contract']);
  git(directory,['config','user.email','validation@example.invalid']);
  return directory;
}
const origin=path.join(temporary,'origin.git');
git(temporary,['-c',`safe.directory=${ROOT}`,'-c',`safe.directory=${ROOT}/.git`,'clone','--quiet','--bare','--no-local',ROOT,origin]);
git(temporary,['--git-dir',origin,'update-ref','refs/heads/main',BASE]);
git(temporary,['--git-dir',origin,'symbolic-ref','HEAD','refs/heads/main']);
const patch=path.join(ROOT,'evidence/41901264550/reverse-ascii.patch');
const prompts=path.join(temporary,'gh-aw/prompts'); fs.mkdirSync(prompts,{recursive:true});
fs.cpSync(path.resolve(native,'../md'),prompts,{recursive:true});
require(path.join(native,'shim.cjs'));
const {createHandlers}=require(path.join(native,'safe_outputs_handlers.cjs'));
const {createAppendFunction}=require(path.join(native,'safe_outputs_append.cjs'));
const {generateGitPatch}=require(path.join(native,'generate_git_patch.cjs'));
const {applyBundleToBranch}=require(path.join(native,'create_pull_request.cjs'));
const lines=fs.readFileSync(path.join(ROOT,'.github/workflows/phase2-next.lock.yml'),'utf8').split('\n');
const line=lines.find(s=>s.includes('GH_AW_SAFE_OUTPUTS_HANDLER_CONFIG: '));
const config=JSON.parse(JSON.parse(line.split('GH_AW_SAFE_OUTPUTS_HANDLER_CONFIG: ')[1]));
for (const object of [config,config.create_pull_request]) for (const key of Object.keys(object)) if (/token/i.test(key)) delete object[key];
assert.equal(config.create_pull_request.draft,true);
assert.equal(config.create_pull_request.preserve_branch_name,true);
assert.equal(config.create_pull_request.branch_prefix,'codex/');
const request={title:'Implement preserved reverseAscii candidate',body:'Implements the approved ASCII-only reversal using the exact candidate from run 41901264550. Eight immutable tests pass after the change. Leave the Draft PR unmerged for human review.',branch:LOCAL,draft:true,base:'main'};
function handler(cwd, output) {
  process.chdir(cwd); process.env.GITHUB_WORKSPACE=cwd;
  fs.writeFileSync(output,'');
  return createHandlers({debug:()=>{}},createAppendFunction(output),config).createPullRequestHandler;
}
async function main() {
  const uncommitted=clone('uncommitted');
  git(uncommitted,['switch','--quiet','-c',LOCAL]); git(uncommitted,['apply','--check',patch]); git(uncommitted,['apply',patch]);
  const rejectedFile=path.join(temporary,'rejected.jsonl');
  const rejected=await handler(uncommitted,rejectedFile)(request);
  assert.equal(rejected.isError,true);
  assert.match(JSON.parse(rejected.content[0].text).error,/No changes to commit/);
  assert.equal(fs.readFileSync(rejectedFile,'utf8'),'');
  const incremental=await generateGitPatch(LOCAL,'main',{mode:'incremental',cwd:uncommitted,incrementalBaseSha:BASE});
  assert.equal(incremental.success,false); // Optional repair also requires commits.

  const agent=clone('committed'); process.env.GITHUB_WORKSPACE=agent;
  python(agent,[path.join(ROOT,'scripts/workspace_guard.py'),'capture','next']);
  git(agent,['switch','--quiet','-c',LOCAL]); git(agent,['apply','--check',patch]); git(agent,['apply',patch]);
  git(agent,['add','--',SOURCE]); git(agent,['commit','--quiet','-m','Implement preserved reverseAscii candidate']);
  const commit=git(agent,['rev-parse','HEAD']).stdout.trim();
  const output=path.join(temporary,'accepted.jsonl');
  const staged=await handler(agent,output)(request);
  assert.notEqual(staged.isError,true,JSON.stringify(staged));
  const response=JSON.parse(staged.content[0].text); assert.equal(response.result,'success');
  const records=fs.readFileSync(output,'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(records.length,1); assert.equal(records[0].type,'create_pull_request');
  assert.equal(records[0].branch,LOCAL); assert.equal(records[0].draft,true); assert.equal(records[0].base_commit,BASE);
  python(agent,[path.join(ROOT,'scripts/workspace_guard.py'),'check','next']);
  const publisher=clone('publisher'); process.chdir(publisher); process.env.GITHUB_WORKSPACE=publisher;
  git(publisher,['bundle','verify',response.bundle.path]);
  assert.equal(git(publisher,['bundle','list-heads',response.bundle.path]).stdout.trim(),`${commit} refs/heads/${LOCAL}`);
  const exec={
    async exec(command,args=[],options={}) { assert.equal(command,'git'); return git(publisher,args).status; },
    async getExecOutput(command,args=[],options={}) { assert.equal(command,'git'); const r=git(publisher,args,!!options.ignoreReturnCode); return {exitCode:r.status,stdout:r.stdout,stderr:r.stderr}; }
  };
  await applyBundleToBranch(response.bundle.path,REMOTE,LOCAL,exec);
  assert.equal(git(publisher,['branch','--show-current']).stdout.trim(),REMOTE);
  assert.equal(git(publisher,['rev-parse','HEAD']).stdout.trim(),commit);
  assert.equal(git(publisher,['rev-list','--parents','-n','1','HEAD']).stdout.trim(),`${commit} ${BASE}`);
  assert.equal(git(publisher,['diff','--name-only',BASE,'HEAD']).stdout.trim(),SOURCE);
  const tested=cp.spawnSync('node',['--test','test/reverse-ascii.test.mjs'],{cwd:publisher,encoding:'utf8',env:process.env});
  assert.equal(tested.status,0,tested.stdout+tested.stderr); assert.match(tested.stdout,/pass 8/);
  assert.notEqual(git(temporary,['--git-dir',origin,'show-ref','--verify',`refs/heads/${REMOTE}`],true).status,0);
  const result={native_pin:PIN,base:BASE,local_branch:LOCAL,publisher_local_branch:REMOTE,commit,
    uncommitted_request:'rejected by native MCP handler',native_intents:1,bundle_verified:true,
    native_import:'passed in real publisher checkout',candidate_tests:8,remote_push:false,github_pr_created:false,
    optional_repair_audit:'native incremental patch rejects uncommitted-only changes; repair authorization remains unchanged'};
  fs.writeFileSync(path.join(temporary,'result.json'),JSON.stringify(result,null,2)+'\n');
  console.log('NATIVE_CONTRACT_PASS '+JSON.stringify(result));
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
