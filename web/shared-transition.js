/**
 * SharedTransitionController
 * Vanilla JS implementation for shared element transitions
 * 
 * Features:
 * - DOM measurement / cloning / animation
 * - Web Animations API usage
 * - Debounce and cancel mechanisms
 * - Reduced motion support
 */

class SharedTransitionController {
    constructor(options = {}) {
        this.container = options.container || document.body;
        this.onStart = options.onStart || (() => { });
        this.onComplete = options.onComplete || (() => { });

        // Track active animations for cancellation
        this.activeAnimations = new Map();
        this.isTransitioning = false;
        this.pendingTransition = null;

        // Check reduced motion preference
        this.prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        // Listen for preference changes
        window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (e) => {
            this.prefersReducedMotion = e.matches;
        });
    }

    /**
     * Get computed CSS variable value
     */
    getCSSVar(name, fallback = '0ms') {
        const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return value || fallback;
    }

    /**
     * Parse duration string to milliseconds
     */
    parseDuration(str) {
        if (str.endsWith('ms')) return parseFloat(str);
        if (str.endsWith('s')) return parseFloat(str) * 1000;
        return parseFloat(str);
    }

    /**
     * Cancel all active animations and snap to final state
     */
    cancelAll() {
        this.activeAnimations.forEach((animation, key) => {
            animation.finish();
        });
        this.activeAnimations.clear();
        this.isTransitioning = false;
    }

    /**
     * Transition a shared element from one position to another
     * Uses FLIP technique: First, Last, Invert, Play
     */
    async transitionSharedElement(element, targetRect, options = {}) {
        const duration = options.duration || this.parseDuration(this.getCSSVar('--shared-duration', '120ms'));
        const easing = options.easing || this.getCSSVar('--transition-ease', 'cubic-bezier(0.2, 0.8, 0.2, 1)');

        // Get current position
        const firstRect = element.getBoundingClientRect();

        // Calculate delta (invert)
        const deltaX = firstRect.left - targetRect.left;
        const deltaY = firstRect.top - targetRect.top;

        // Skip if no movement needed
        if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) {
            return Promise.resolve();
        }

        // Add will-change hint
        element.classList.add('shared-animating');

        // Animate using Web Animations API
        const animation = element.animate([
            { transform: `translate(${deltaX}px, ${deltaY}px)` },
            { transform: 'translate(0, 0)' }
        ], {
            duration: this.prefersReducedMotion ? 0 : duration,
            easing: easing,
            fill: 'forwards'
        });

        // Track animation
        const animationId = Symbol('sharedElement');
        this.activeAnimations.set(animationId, animation);

        return animation.finished.then(() => {
            this.activeAnimations.delete(animationId);
            element.classList.remove('shared-animating');
            // Clear inline transform
            element.style.transform = '';
        });
    }

    /**
     * Fade out an element
     */
    async fadeOut(element, options = {}) {
        const duration = options.duration || this.parseDuration(this.getCSSVar('--exit-duration', '120ms'));
        const easing = options.easing || this.getCSSVar('--transition-ease');

        element.classList.add('shared-animating');

        const animation = element.animate([
            { opacity: 1 },
            { opacity: 0 }
        ], {
            duration: this.prefersReducedMotion ? this.parseDuration(this.getCSSVar('--reduced-fade-duration', '60ms')) : duration,
            easing: easing,
            fill: 'forwards'
        });

        const animationId = Symbol('fadeOut');
        this.activeAnimations.set(animationId, animation);

        return animation.finished.then(() => {
            this.activeAnimations.delete(animationId);
            element.classList.remove('shared-animating');
        });
    }

    /**
     * Fade in an element with optional translate
     */
    async fadeIn(element, options = {}) {
        const duration = options.duration || this.parseDuration(this.getCSSVar('--enter-duration', '180ms'));
        const easing = options.easing || this.getCSSVar('--transition-ease');
        const translateDistance = options.translate || this.getCSSVar('--translate-distance', '10px');

        element.classList.add('shared-animating');

        const keyframes = this.prefersReducedMotion
            ? [{ opacity: 0 }, { opacity: 1 }]
            : [
                { opacity: 0, transform: `translateY(${translateDistance})` },
                { opacity: 1, transform: 'translateY(0)' }
            ];

        const animation = element.animate(keyframes, {
            duration: this.prefersReducedMotion ? this.parseDuration(this.getCSSVar('--reduced-fade-duration', '60ms')) : duration,
            easing: easing,
            fill: 'forwards'
        });

        const animationId = Symbol('fadeIn');
        this.activeAnimations.set(animationId, animation);

        return animation.finished.then(() => {
            this.activeAnimations.delete(animationId);
            element.classList.remove('shared-animating');
            element.style.opacity = '';
            element.style.transform = '';
        });
    }

    /**
     * Crossfade between two elements (e.g., header titles)
     */
    async crossfade(outElement, inElement, options = {}) {
        const duration = options.duration || this.parseDuration(this.getCSSVar('--header-crossfade', '100ms'));

        // Position incoming element
        inElement.style.opacity = '0';
        inElement.style.position = 'absolute';
        inElement.style.top = '0';
        inElement.style.left = '0';

        const fadeOutAnim = outElement.animate([
            { opacity: 1 },
            { opacity: 0 }
        ], {
            duration: this.prefersReducedMotion ? 0 : duration,
            easing: 'ease-out',
            fill: 'forwards'
        });

        const fadeInAnim = inElement.animate([
            { opacity: 0 },
            { opacity: 1 }
        ], {
            duration: this.prefersReducedMotion ? 0 : duration,
            easing: 'ease-in',
            fill: 'forwards'
        });

        const animId1 = Symbol('crossfadeOut');
        const animId2 = Symbol('crossfadeIn');
        this.activeAnimations.set(animId1, fadeOutAnim);
        this.activeAnimations.set(animId2, fadeInAnim);

        return Promise.all([fadeOutAnim.finished, fadeInAnim.finished]).then(() => {
            this.activeAnimations.delete(animId1);
            this.activeAnimations.delete(animId2);
            outElement.style.display = 'none';
            inElement.style.position = '';
            inElement.style.opacity = '';
        });
    }

    /**
     * Stagger animate a list of children
     */
    async staggerChildren(container, options = {}) {
        const staggerDelay = options.stagger || this.parseDuration(this.getCSSVar('--stagger-item', '24ms'));
        const children = Array.from(container.children);

        if (this.prefersReducedMotion) {
            // No stagger in reduced motion
            return this.fadeIn(container);
        }

        const promises = children.map((child, index) => {
            return new Promise(resolve => {
                setTimeout(() => {
                    this.fadeIn(child).then(resolve);
                }, index * staggerDelay);
            });
        });

        return Promise.all(promises);
    }

    /**
     * Main panel transition orchestrator
     * Handles the full flow: shared element move → exit → swap → enter
     */
    async transitionPanel({
        sharedElement,        // Element that moves between panels (e.g., active indicator)
        sharedTargetRect,     // Target rect for shared element
        oldContent,           // Current content panel
        newContent,           // New content panel (hidden)
        oldHeader,            // Current header element (optional)
        newHeader,            // New header element (optional)
        onSwap                // Callback to perform DOM swap
    }) {
        // Debounce: cancel any in-progress transition
        if (this.isTransitioning) {
            this.cancelAll();
        }

        this.isTransitioning = true;
        this.onStart();

        try {
            // Phase 1: Move shared element (if provided)
            const sharedPromise = sharedElement && sharedTargetRect
                ? this.transitionSharedElement(sharedElement, sharedTargetRect)
                : Promise.resolve();

            // Phase 2: Fade out old content (runs in parallel with shared element)
            const exitPromise = oldContent
                ? this.fadeOut(oldContent)
                : Promise.resolve();

            // Wait for both
            await Promise.all([sharedPromise, exitPromise]);

            // Phase 3: DOM swap
            if (onSwap) {
                await onSwap();
            }

            // Phase 4: Show and animate in new content
            if (newContent) {
                newContent.style.display = '';
                await this.fadeIn(newContent);
            }

            // Phase 5: Crossfade header (if provided)
            if (oldHeader && newHeader) {
                await this.crossfade(oldHeader, newHeader);
            }

            this.isTransitioning = false;
            this.onComplete();

        } catch (error) {
            console.error('Transition error:', error);
            this.isTransitioning = false;
            // Ensure we end up in a valid state
            if (oldContent) oldContent.style.display = 'none';
            if (newContent) {
                newContent.style.display = '';
                newContent.style.opacity = '1';
            }
        }
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { SharedTransitionController };
}
