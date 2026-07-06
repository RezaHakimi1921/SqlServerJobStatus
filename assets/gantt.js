(function () {
    function scrollGanttToNow() {
        var wrapper = document.getElementById('gantt-timeline-scroll');
        var nowLine = document.getElementById('gantt-now-line');
        if (!wrapper || !nowLine) return;
        var nowLeft = parseFloat(nowLine.style.left) || 0;
        var target = nowLeft - wrapper.clientWidth * 0.55;
        wrapper.scrollLeft = Math.max(0, target);
    }

    function syncGanttVerticalScroll() {
        var timeline = document.getElementById('gantt-timeline-scroll');
        var labels = document.getElementById('gantt-labels');
        if (!timeline || !labels) return;
        if (timeline.dataset.vsyncInit === '1') return;
        timeline.dataset.vsyncInit = '1';

        var syncing = false;
        function mirror(from, to) {
            if (syncing) return;
            syncing = true;
            to.scrollTop = from.scrollTop;
            syncing = false;
        }

        timeline.addEventListener('scroll', function () {
            mirror(timeline, labels);
        });
    }

    function initGanttDrag(wrapper) {
        if (!wrapper || wrapper.dataset.dragInit === '1') return;
        wrapper.dataset.dragInit = '1';
        var dragging = false;
        var startX = 0;
        var scrollStart = 0;

        wrapper.addEventListener('mousedown', function (e) {
            if (e.button !== 0) return;
            dragging = true;
            wrapper.classList.add('dragging');
            startX = e.clientX;
            scrollStart = wrapper.scrollLeft;
            e.preventDefault();
        });

        document.addEventListener('mouseup', function () {
            if (!dragging) return;
            dragging = false;
            wrapper.classList.remove('dragging');
        });

        wrapper.addEventListener('mousemove', function (e) {
            if (!dragging) return;
            e.preventDefault();
            var dx = e.clientX - startX;
            wrapper.scrollLeft = scrollStart - dx;
        });

        wrapper.addEventListener('mouseleave', function () {
            dragging = false;
            wrapper.classList.remove('dragging');
        });
    }

    function setupGantt() {
        var wrapper = document.getElementById('gantt-timeline-scroll');
        if (!wrapper) return;
        initGanttDrag(wrapper);
        syncGanttVerticalScroll();
        scrollGanttToNow();
    }

    var observer = new MutationObserver(function () {
        var wrapper = document.getElementById('gantt-timeline-scroll');
        if (wrapper) wrapper.dataset.vsyncInit = '0';
        setupGantt();
    });

    function watchGantt() {
        var area = document.getElementById('gantt-chart-area');
        if (area) {
            observer.observe(area, { childList: true, subtree: true });
            setupGantt();
        } else {
            setTimeout(watchGantt, 500);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', watchGantt);
    } else {
        watchGantt();
    }
})();
