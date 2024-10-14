const socket = io();

socket.on('connect', function() {
    console.log('Connected to server');
    socket.emit('get_initial_status');
});

socket.on('status_update', function(data) {
    console.log('Received status update:', data);
    document.getElementById('total-add-count').textContent = data.total_add_count;
    document.getElementById('total-rem-count').textContent = data.total_rem_count;
    document.getElementById('lock-status').textContent = data.lock_state ? 'Locked' : 'Unlocked';
    document.getElementById('lid-status').textContent = data.lid_closed ? 'Closed' : 'Open';
    document.getElementById('remaining-time').textContent = data.remaining_time;

    // Update the form fields with the latest values
    document.getElementById('drink-limit').value = data.drink_limit;
    document.getElementById('cycle-duration').value = data.cycle_duration;
});

document.getElementById('settings-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());

    socket.emit('update_settings', data, function(response) {
        if (response.status === 'success') {
            alert('Settings updated successfully');
        } else {
            alert('Failed to update settings: ' + response.message);
        }
    });
});

document.getElementById('reset-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());

    socket.emit('reset_device', data, function(response) {
        if (response.status === 'success') {
            alert('Device reset successfully');
        } else {
            alert('Failed to reset device: ' + response.message);
        }
    });
});