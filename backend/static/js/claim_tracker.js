document.addEventListener("DOMContentLoaded", function(){

    const trackers = document.querySelectorAll(".claim-tracker");

    trackers.forEach(tracker => {

        const status = tracker.dataset.status;

        const steps = tracker.querySelectorAll(".step");

        const map = {
            "pending":0,
            "approved":1,
            "open":2,
            "settled":3
        };

        if(status === "rejected"){
            steps.forEach(step=>{
                step.classList.add("rejected");
            });
            return;
        }

        const activeIndex = map[status];

        steps.forEach((step,index)=>{

            if(index < activeIndex){
                step.classList.add("completed");
            }

            if(index === activeIndex){
                step.classList.add("active");
            }

        });

    });

});
