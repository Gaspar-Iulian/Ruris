export default async function stopRealServer() {
  if (process.env.RURIS_REAL_API === '1') {
    const response = await fetch('http://127.0.0.1:5201/__test__/stop', { method: 'POST' });
    if (!response.ok) throw new Error('The isolated browser test server did not stop cleanly.');
  }
}
