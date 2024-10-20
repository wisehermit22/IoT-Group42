const socket = io();

socket.on('connect', function() {
    console.log('Connected to server');
    socket.emit('get_initial_status');
    fetchConsumptionHistory();
});

socket.on('status_update', function(data) {
    console.log('Received status update:', data);
    updateStatusDisplay(data);
    fetchConsumptionHistory();
});

function updateStatusDisplay(data) {
    document.getElementById('inventory-count').textContent = data.inventory_count;
    document.getElementById('total-add-count').textContent = data.added_count;
    document.getElementById('total-rem-count').textContent = data.consumption_count;
    document.getElementById('consumption-limit').textContent = data.consumption_limit;
    document.getElementById('lock-status').textContent = data.lock_status ? 'Locked' : 'Unlocked';
    document.getElementById('lid-status').textContent = data.lid_status ? 'Closed' : 'Open';
    document.getElementById('remaining-time').textContent = data.lockout_remaining;
    document.getElementById('cycle-end-time').textContent = data.cycle_end_time;
    document.getElementById('current-streak').textContent = data.current_streak;
    document.getElementById('highest-streak').textContent = data.highest_streak;
}


function updateStreakDisplay(data) {
    document.getElementById('current-streak').textContent = data.current_streak;
    document.getElementById('highest-streak').textContent = data.highest_streak;
}


let consumptionChart = null;

function createConsumptionChart(history) {
    const ctx = document.getElementById('consumptionChart').getContext('2d');
    
    const labels = history.map(entry => {
        const date = new Date(entry.cycle_start);
        date.setHours(date.getHours() + 8);
        return date.toLocaleString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit', 
            hour12: true 
        });
    });
    const consumptionData = history.map(entry => entry.count);
    const limitExceeded = history.map(entry => {
        if (entry.count < entry.consumption_limit) {
            return 'rgba(75, 192, 192, 0.7)';  // Softer teal color
        } else if (entry.count === entry.consumption_limit) {
            return 'rgba(255, 206, 86, 0.7)';  // Softer yellow
        } else {
            return 'rgba(255, 99, 132, 0.7)';  // Softer red
        }
    });

    const chartConfig = {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Drinks Consumed',
                data: consumptionData,
                backgroundColor: limitExceeded,
                borderColor: limitExceeded,
                borderWidth: 1,
                borderRadius: 3,  // Rounded corners on bars
                maxBarThickness: 50  // Limit maximum bar width
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: {
                    top: 25,
                    right: 25
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Number of Drinks',
                        padding: 10,
                        font: {
                            family: "'Montserrat', sans-serif",
                            size: 14,
                            weight: 'bold'
                        },
                        
                    },
                    ticks: {
                        stepSize: 1,
                        precision: 0,
                        font: {
                            family: "'Montserrat', sans-serif",
                            size: 12
                        }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.1)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Consumption Cycle',
                        padding: 10,
                        font: {
                            family: "'Montserrat', sans-serif",
                            size: 14,
                            weight: 'bold'
                        }
                    },
                    ticks: {
                        maxRotation: 75,
                        minRotation: 75,
                        font: {
                            family: "'Montserrat', sans-serif",
                            size: 10
                        },
                        color: 'rgba(0, 0, 0, 0.7)'
                    },
                    grid: {
                        display: false
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(0, 0, 0, 0.7)',
                    titleFont: {
                        family: "'Montserrat', sans-serif",
                        size: 14,
                        weight: 'bold'
                    },
                    bodyFont: {
                        family: "'Montserrat', sans-serif",
                        size: 12
                    },
                    padding: 10,
                    callbacks: {
                        label: function(context) {
                            const dataIndex = context.dataIndex;
                            const entry = history[dataIndex];
                            let limitStatus;
                            if (entry.count < entry.consumption_limit) {
                                limitStatus = 'Not Exceeded';
                            } else if (entry.count === entry.consumption_limit) {
                                limitStatus = 'Limit Reached';
                            } else {
                                limitStatus = 'Exceeded';
                            }
                            return [
                                `Drinks: ${entry.count}`,
                                `Limit: ${entry.consumption_limit}`,
                                `Status: ${limitStatus}`
                            ];
                        },
                        title: function(tooltipItems) {
                            const dataIndex = tooltipItems[0].dataIndex;
                            const entry = history[dataIndex];
                            const date = new Date(entry.cycle_start);
                            date.setHours(date.getHours() + 8);
                            return date.toLocaleString();
                        }
                    }
                }
            }
        }
    };

    if (consumptionChart) {
        // Update existing chart data
        consumptionChart.data.labels = labels;
        consumptionChart.data.datasets[0].data = consumptionData;
        consumptionChart.data.datasets[0].backgroundColor = limitExceeded;
        consumptionChart.data.datasets[0].borderColor = limitExceeded;
        consumptionChart.options = chartConfig.options;  // Update options including tooltip
        consumptionChart.update();
    } else {
        // Create new chart
        consumptionChart = new Chart(ctx, chartConfig);
    }
}


function fetchConsumptionHistory() {
    fetch('/api/consumption_history')
        .then(response => response.json())
        .then(data => {
            updateStreakDisplay(data);
            createConsumptionChart(data.history.reverse()); // Reverse to show oldest first
        })
        .catch(error => console.error('Error fetching consumption history:', error));
}


document.getElementById('settings-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    const submitButton = this.querySelector('button[type="submit"]');
    const originalText = submitButton.textContent;

    submitButton.textContent = 'Updating...';
    submitButton.disabled = true;

    socket.emit('update_settings', data, function(response) {
        if (response.status === 'success') {
            showToast('Settings updated successfully', 'success');
        } else {
            showToast('Failed to update settings: ' + response.message, 'error');
        }
        submitButton.textContent = originalText;
        submitButton.disabled = false;
    });
});

document.getElementById('reset-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    const submitButton = this.querySelector('button[type="submit"]');
    const originalText = submitButton.textContent;

    submitButton.textContent = 'Resetting...';
    submitButton.disabled = true;

    socket.emit('reset_device', data, function(response) {
        if (response.status === 'success') {
            showToast('Device reset successfully', 'success');
        } else {
            showToast('Failed to reset device: ' + response.message, 'error');
        }
        submitButton.textContent = originalText;
        submitButton.disabled = false;
    });
});

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.textContent = message;
    toast.className = `fixed bottom-4 right-4 p-4 rounded-md text-white ${type === 'success' ? 'bg-green-500' : 'bg-red-500'} transition-opacity duration-300`;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            document.body.removeChild(toast);
        }, 300);
    }, 3000);
}

window.addEventListener('resize', function() {
    fetchConsumptionHistory(); // This will recreate the chart
});

// Initial fetch
fetchConsumptionHistory();