(function () {
    function safeGet(id) {
        return document.getElementById(id);
    }

    function setModalOpen(modal, isOpen) {
        if (!modal) return;

        if (isOpen) {
            modal.classList.add('is-open');
            modal.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
        } else {
            modal.classList.remove('is-open');
            modal.setAttribute('aria-hidden', 'true');
            document.body.style.overflow = '';
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var downloadBtn = safeGet('downloadBtn');
        var modal = safeGet('downloadModal');

        if (!downloadBtn || !modal) return;

        downloadBtn.addEventListener('click', function (e) {
            e.preventDefault();
            setModalOpen(modal, true);
        });

        modal.addEventListener('click', function (e) {
            var target = e.target;
            if (!target) return;

            if (target.matches('[data-modal-close]')) {
                setModalOpen(modal, false);
            }
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                setModalOpen(modal, false);
            }
        });
    });
})();
