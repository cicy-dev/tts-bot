console.log('Simple test back to working method');
window.inspectAll = () => {
  console.log('inspectAll called');
  try {
    if (!window.__m) console.log('No __m');
    else console.log('Keys:', Object.keys(window.__m));
  } catch(e) {
    console.error('Error:', e);
  }
};
window.inspectAll();