// Optical presence — the camera watches for a face, or failing that for motion.
// It recognises nobody by design: "NO MATCH" is the truth, not a tease. Kept as
// a module of its own so the redesign can summon it into the subject layer
// without a permanent camera card on screen.

const $ = (sel) => document.querySelector(sel);
const vision = { on: false, present: false, prev: null, stream: null };

/** The idle loop — Red John's mark turning while the camera is stood down. */
export function mountRedJohn() {
  const frame = $('#rj-frame');
  const clip = $('#rj-loop');
  if (!clip) return;
  clip.addEventListener('playing', () => frame.classList.add('has-loop'), { once: true });
  clip.addEventListener('error', () => frame.classList.remove('has-loop'));
  clip.play().catch(() => {});
}

export function isArmed() { return vision.on; }

export async function startVision(onState) {
  const video = $('#cam');
  const status = $('#rj-status');
  try {
    vision.stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 320, height: 240 }, audio: false,
    });
  } catch {
    if (status) status.textContent = 'CAMERA OFFLINE';
    return false;
  }
  video.srcObject = vision.stream;
  await video.play().catch(() => {});
  vision.on = true;
  $('#rj-frame').classList.add('armed');
  const clip = $('#rj-loop');
  if (clip) clip.pause();
  const detector = 'FaceDetector' in window
    ? new window.FaceDetector({ fastMode: true, maxDetectedFaces: 3 })
    : null;
  loop(video, status, detector, onState);
  return true;
}

export function stopVision(onState) {
  vision.on = false;
  if (vision.stream) for (const track of vision.stream.getTracks()) track.stop();
  vision.stream = null;
  vision.present = false;
  const status = $('#rj-status');
  if (status) status.textContent = 'OPTICAL STANDBY';
  $('#rj-frame').classList.remove('armed', 'hit');
  const clip = $('#rj-loop');
  if (clip) clip.play().catch(() => {});
  if (onState) onState(false);
}

// A 64x48 thumbnail is plenty for a motion score and costs almost nothing.
const thumb = document.createElement('canvas');
thumb.width = 64;
thumb.height = 48;
const thumbCtx = thumb.getContext('2d', { willReadFrequently: true });

function motionScore(video) {
  thumbCtx.drawImage(video, 0, 0, thumb.width, thumb.height);
  const frame = thumbCtx.getImageData(0, 0, thumb.width, thumb.height).data;
  const grey = new Uint8Array(frame.length / 4);
  for (let i = 0, g = 0; i < frame.length; i += 4, g++) {
    grey[g] = (frame[i] * 299 + frame[i + 1] * 587 + frame[i + 2] * 114) / 1000;
  }
  if (!vision.prev) { vision.prev = grey; return 0; }
  let changed = 0;
  for (let i = 0; i < grey.length; i++) {
    if (Math.abs(grey[i] - vision.prev[i]) > 18) changed++;
  }
  vision.prev = grey;
  return changed / grey.length;
}

async function loop(video, status, detector, onState) {
  while (vision.on) {
    let faces = 0;
    let present = false;
    let method = 'motion';
    try {
      if (detector) {
        method = 'face';
        faces = (await detector.detect(video)).length;
        present = faces > 0;
      } else {
        present = motionScore(video) > 0.035;
      }
    } catch {
      present = false;
    }
    paint(status, present, faces, method);
    if (present !== vision.present) {
      vision.present = present;
      if (onState) onState(present, { faces, method });
    }
    await new Promise((r) => setTimeout(r, 700));
  }
}

function paint(status, present, faces, method) {
  const frame = $('#rj-frame');
  if (frame) frame.classList.toggle('hit', present);
  if (!status) return;
  if (!present) { status.textContent = 'NO MATCH'; return; }
  status.textContent = method === 'face'
    ? `PRESENCE · ${faces} · NO MATCH`
    : 'PRESENCE · NO MATCH';
}
