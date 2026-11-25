document.addEventListener('DOMContentLoaded', function() {
        function updateShift() {
            const now = new Date();
            const hour = now.getHours();
            const minutes = now.getMinutes();
            const timeInMinutes = hour * 60 + minutes;
            const dayOfWeek = now.getDay(); // Sunday is 0
            
            // Format current time in military time (HH:MM)
            const militaryTime = String(hour).padStart(2, '0') + ':' + String(minutes).padStart(2, '0');
            
            let shift = "Off-Shift";
            
            if (dayOfWeek === 0) {
                // SUNDAY SCHEDULE
                if (timeInMinutes >= 8 * 60 && timeInMinutes < 11 * 60) {
                    shift = "Morning";
                } else if (timeInMinutes >= 11 * 60 && timeInMinutes < 14 * 60) {
                    shift = "Afternoon";
                }
            } else {
                // MONDAY - SATURDAY SCHEDULE
                if (timeInMinutes >= 1 * 60 && timeInMinutes < 5 * 60) {
                    shift = "Overnight";
                } else if (timeInMinutes >= 6 * 60 + 45 && timeInMinutes < 10 * 60 + 15) {
                    shift = "Morning";
                } else if (timeInMinutes >= 10 * 60 + 15 && timeInMinutes < 13 * 60 + 15) {
                    shift = "Afternoon";
                } else if (timeInMinutes >= 13 * 60 + 15 && timeInMinutes < 17 * 60) {
                    shift = "Evening";
                }
            }
            
            document.getElementById('shift-display').textContent = `${militaryTime} | Shift: ${shift}`;
        }
        
        updateShift();
        setInterval(updateShift, 60000); // Poll every 60 seconds
    });
