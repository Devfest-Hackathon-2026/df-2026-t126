import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, before, test } from 'node:test';
import { assertFails, assertSucceeds, initializeTestEnvironment } from '@firebase/rules-unit-testing';
import { doc, getDoc, setDoc, collection, getDocs, onSnapshot } from 'firebase/firestore';
import { ref, uploadBytes, getBytes } from 'firebase/storage';

const projectId = 'demo-gesture-relay';
const loopback = (value) => value && /^(127\.0\.0\.1|localhost):\d+$/.test(value);
if (!loopback(process.env.FIRESTORE_EMULATOR_HOST) || !loopback(process.env.FIREBASE_STORAGE_EMULATOR_HOST)) {
  throw new Error('Explicit loopback emulator endpoints required; production fallback forbidden');
}
let env;
before(async () => {
  env = await initializeTestEnvironment({projectId,
    firestore: {rules: await readFile(new URL('../../firestore.rules', import.meta.url), 'utf8')},
    storage: {rules: await readFile(new URL('../../storage.rules', import.meta.url), 'utf8')},
  });
  await env.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore();
    for (const [path, value] of Object.entries({
      'rooms/r': {status: 'playing'},
      'rooms/r/players/alice': {phase: 'playing'},
      'rooms/r/rounds/g': {status: 'playing'},
      'rooms/r/rounds/g/steps/0': {status: 'done'},
      'rooms/r/rounds/g/private/main': {odai_text: 'secret', players: {alice: 'A'}},
      'rooms/r/rounds/g/assets/image': {path: 'secret.png'},
      'rooms/r/rounds/g/jobs/job': {status: 'pending'},
      'rooms/r/rounds/g/gesture_batches/0': {samples: []},
      'rooms/r/rounds/g/result/final': {odai: 'secret'},
      'join_codes/1234': {room_id: 'r'},
      'config/game': {text_seconds: 60},
      'round_lookup/g': {room_id: 'r'},
      'requests/key': {response: {}},
      'task_outbox/key': {sent: false},
      'cleanup_outbox/key': {round_id: 'g'},
      'progress_outbox/key': {payload: {job_id: 'j'}},
      'execution_outbox/key': {payload: {job_id: 'j'}},
      'rooms/reused': {status: 'waiting', current_round_id: 'old'},
      'rooms/reused/players/alice': {phase: 'lobby'},
      'rooms/reused/players/newcomer': {phase: 'lobby'},
      'rooms/reused/rounds/old': {status: 'finished'},
      'rooms/reused/rounds/old/steps/0': {status: 'done', player_id: 'former'},
      'rooms/reused/rounds/old/private/main': {players: {alice: 'A', former: 'B'}},
    })) await setDoc(doc(db, path), value);
  });
});
after(async () => { if (env) await env.cleanup(); });

test('members can subscribe to public round and step state', async () => {
  const db = env.authenticatedContext('alice').firestore();
  for (const path of ['rooms/r', 'rooms/r/players/alice', 'rooms/r/rounds/g', 'rooms/r/rounds/g/steps/0']) {
    await assertSucceeds(getDoc(doc(db, path)));
  }
  await assertSucceeds(getDocs(collection(db, 'rooms/r/rounds/g/steps')));
});

test('anonymous visitors and nonmembers cannot read public state', async () => {
  for (const context of [env.unauthenticatedContext(), env.authenticatedContext('outsider')]) {
    await assertFails(getDoc(doc(context.firestore(), 'rooms/r/rounds/g')));
  }
});

test('a new lobby member cannot read past round state or enumerate rounds', async () => {
  const db = env.authenticatedContext('newcomer').firestore();
  await assertSucceeds(getDoc(doc(db, 'rooms/reused')));
  await assertFails(getDoc(doc(db, 'rooms/reused/rounds/old')));
  await assertFails(getDoc(doc(db, 'rooms/reused/rounds/old/steps/0')));
  await assertFails(getDocs(collection(db, 'rooms/reused/rounds/old/steps')));
  await assertFails(getDocs(collection(db, 'rooms/reused/rounds')));
});

test('old round state still requires both room and round membership', async () => {
  const retained = env.authenticatedContext('alice').firestore();
  const departed = env.authenticatedContext('former').firestore();
  await assertSucceeds(getDoc(doc(retained, 'rooms/reused/rounds/old')));
  await assertSucceeds(getDocs(collection(retained, 'rooms/reused/rounds/old/steps')));
  await assertFails(getDoc(doc(departed, 'rooms/reused/rounds/old')));
  await assertFails(getDocs(collection(departed, 'rooms/reused/rounds/old/steps')));
  await assertFails(getDocs(collection(retained, 'rooms/reused/rounds')));
});

test('a new room member can subscribe to the round they join', {timeout: 5000}, async () => {
  await env.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore();
    await setDoc(doc(db, 'rooms/reused'), {status: 'playing', current_round_id: 'next'});
    await setDoc(doc(db, 'rooms/reused/rounds/next'), {status: 'playing'});
    await setDoc(doc(db, 'rooms/reused/rounds/next/private/main'), {players: {newcomer: 'A'}});
    await setDoc(doc(db, 'rooms/reused/rounds/next/steps/0'), {status: 'active'});
  });
  const db = env.authenticatedContext('newcomer').firestore();
  for (const ref of [doc(db, 'rooms/reused/rounds/next'), collection(db, 'rooms/reused/rounds/next/steps')]) {
    let stop;
    try {
      const snapshot = await new Promise((resolve, reject) => {
        stop = onSnapshot(ref, {includeMetadataChanges: true}, (value) => {
          if (!value.metadata.fromCache) resolve(value);
        }, reject);
      });
      assert.ok(snapshot.exists ? snapshot.exists() : snapshot.size === 1);
    } finally {
      stop?.();
    }
  }
});

test('even members cannot read content, jobs, lookup, config or outboxes directly', async () => {
  const db = env.authenticatedContext('alice').firestore();
  for (const path of ['private/main', 'assets/image', 'jobs/job', 'gesture_batches/0', 'result/final']) {
    await assertFails(getDoc(doc(db, `rooms/r/rounds/g/${path}`)));
  }
  for (const path of ['join_codes/1234', 'config/game', 'round_lookup/g', 'requests/key',
                      'task_outbox/key', 'cleanup_outbox/key', 'progress_outbox/key', 'execution_outbox/key']) {
    await assertFails(getDoc(doc(db, path)));
  }
});

test('clients cannot write state, impersonate members or enumerate rooms/codes', async () => {
  for (const uid of ['alice', 'outsider']) {
    const db = env.authenticatedContext(uid).firestore();
    for (const path of ['rooms/r', `rooms/r/players/${uid}`, 'rooms/r/rounds/g/steps/0']) {
      await assertFails(setDoc(doc(db, path), {status: 'done'}));
    }
    await assertFails(getDocs(collection(db, 'rooms')));
    await assertFails(getDocs(collection(db, 'join_codes')));
  }
});

test('Storage reads and writes are denied for all browser clients', async () => {
  for (const context of [env.unauthenticatedContext(), env.authenticatedContext('alice')]) {
    const object = ref(context.storage(), 'rooms/r/rounds/g/videos/v.mp4');
    await assertFails(uploadBytes(object, new Uint8Array([0, 1, 2])));
    await assertFails(getBytes(object));
  }
});
