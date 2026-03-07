/**
 * useSharedTransition React Hook
 * Coordinates measurement, cloning, and animation for shared element transitions
 * 
 * @param {Object} options
 * @param {string[]} options.sharedKeys - Array of keys identifying shared elements
 * @param {Function} options.onStart - Callback when transition starts
 * @param {Function} options.onComplete - Callback when transition completes
 * 
 * @example
 * const { registerElement, triggerTransition, isTransitioning } = useSharedTransition({
 *   sharedKeys: ['activeIndicator', 'headerTitle'],
 *   onStart: () => console.log('started'),
 *   onComplete: () => console.log('done')
 * });
 */

import { useRef, useCallback, useEffect, useState } from 'react';

// ============================================
// CSS VARIABLE HELPERS
// ============================================

function getCSSVar(name, fallback = '0ms') {
    if (typeof window === 'undefined') return fallback;
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
}

function parseDuration(str) {
    if (str.endsWith('ms')) return parseFloat(str);
    if (str.endsWith('s')) return parseFloat(str) * 1000;
    return parseFloat(str);
}

// ============================================
// REDUCED MOTION HOOK
// ============================================

export function usePrefersReducedMotion() {
    const [prefersReduced, setPrefersReduced] = useState(() => {
        if (typeof window === 'undefined') return false;
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    });

    useEffect(() => {
        const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
        const handler = (e) => setPrefersReduced(e.matches);
        mediaQuery.addEventListener('change', handler);
        return () => mediaQuery.removeEventListener('change', handler);
    }, []);

    return prefersReduced;
}

// ============================================
// MAIN HOOK
// ============================================

export function useSharedTransition(options = {}) {
    const {
        sharedKeys = [],
        onStart = () => { },
        onComplete = () => { }
    } = options;

    // Element registry: maps keys to DOM elements
    const elementsRef = useRef(new Map());

    // Track active animations for cancellation
    const animationsRef = useRef(new Map());

    // Transition state
    const [isTransitioning, setIsTransitioning] = useState(false);

    // Check reduced motion
    const prefersReducedMotion = usePrefersReducedMotion();

    /**
     * Register a DOM element with a key
     * Use this as a ref callback
     */
    const registerElement = useCallback((key) => {
        return (element) => {
            if (element) {
                elementsRef.current.set(key, element);
            } else {
                elementsRef.current.delete(key);
            }
        };
    }, []);

    /**
     * Get a registered element by key
     */
    const getElement = useCallback((key) => {
        return elementsRef.current.get(key);
    }, []);

    /**
     * Cancel all active animations and snap to final state
     */
    const cancelAll = useCallback(() => {
        animationsRef.current.forEach((animation) => {
            animation.finish();
        });
        animationsRef.current.clear();
        setIsTransitioning(false);
    }, []);

    /**
     * Measure element position (getBoundingClientRect wrapper)
     */
    const measureElement = useCallback((keyOrElement) => {
        const element = typeof keyOrElement === 'string'
            ? elementsRef.current.get(keyOrElement)
            : keyOrElement;

        if (!element) return null;
        return element.getBoundingClientRect();
    }, []);

    /**
     * Animate transform from one position to another (FLIP technique)
     */
    const animateTransform = useCallback(async (element, fromRect, toRect, customDuration) => {
        if (!element || !fromRect || !toRect) return Promise.resolve();

        const duration = customDuration ?? parseDuration(getCSSVar('--shared-duration', '120ms'));
        const easing = getCSSVar('--transition-ease', 'cubic-bezier(0.2, 0.8, 0.2, 1)');

        const deltaX = fromRect.left - toRect.left;
        const deltaY = fromRect.top - toRect.top;

        // Skip if no movement needed
        if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) {
            return Promise.resolve();
        }

        element.classList.add('shared-animating');

        const animation = element.animate([
            { transform: `translate(${deltaX}px, ${deltaY}px)` },
            { transform: 'translate(0, 0)' }
        ], {
            duration: prefersReducedMotion ? 0 : duration,
            easing,
            fill: 'forwards'
        });

        const animationId = Symbol('transform');
        animationsRef.current.set(animationId, animation);

        return animation.finished.then(() => {
            animationsRef.current.delete(animationId);
            element.classList.remove('shared-animating');
            element.style.transform = '';
        });
    }, [prefersReducedMotion]);

    /**
     * Fade out an element
     */
    const fadeOut = useCallback(async (element, customDuration) => {
        if (!element) return Promise.resolve();

        const duration = customDuration ?? parseDuration(getCSSVar('--exit-duration', '120ms'));
        const easing = getCSSVar('--transition-ease');

        element.classList.add('shared-animating');

        const animation = element.animate([
            { opacity: 1 },
            { opacity: 0 }
        ], {
            duration: prefersReducedMotion
                ? parseDuration(getCSSVar('--reduced-fade-duration', '60ms'))
                : duration,
            easing,
            fill: 'forwards'
        });

        const animationId = Symbol('fadeOut');
        animationsRef.current.set(animationId, animation);

        return animation.finished.then(() => {
            animationsRef.current.delete(animationId);
            element.classList.remove('shared-animating');
        });
    }, [prefersReducedMotion]);

    /**
     * Fade in an element with optional translate
     */
    const fadeIn = useCallback(async (element, customDuration) => {
        if (!element) return Promise.resolve();

        const duration = customDuration ?? parseDuration(getCSSVar('--enter-duration', '180ms'));
        const easing = getCSSVar('--transition-ease');
        const translateDistance = getCSSVar('--translate-distance', '10px');

        element.classList.add('shared-animating');

        const keyframes = prefersReducedMotion
            ? [{ opacity: 0 }, { opacity: 1 }]
            : [
                { opacity: 0, transform: `translateY(${translateDistance})` },
                { opacity: 1, transform: 'translateY(0)' }
            ];

        const animation = element.animate(keyframes, {
            duration: prefersReducedMotion
                ? parseDuration(getCSSVar('--reduced-fade-duration', '60ms'))
                : duration,
            easing,
            fill: 'forwards'
        });

        const animationId = Symbol('fadeIn');
        animationsRef.current.set(animationId, animation);

        return animation.finished.then(() => {
            animationsRef.current.delete(animationId);
            element.classList.remove('shared-animating');
            element.style.opacity = '';
            element.style.transform = '';
        });
    }, [prefersReducedMotion]);

    /**
     * Crossfade between two elements
     */
    const crossfade = useCallback(async (outElement, inElement, customDuration) => {
        if (!outElement || !inElement) return Promise.resolve();

        const duration = customDuration ?? parseDuration(getCSSVar('--header-crossfade', '100ms'));

        inElement.style.opacity = '0';

        const fadeOutAnim = outElement.animate([
            { opacity: 1 },
            { opacity: 0 }
        ], {
            duration: prefersReducedMotion ? 0 : duration,
            easing: 'ease-out',
            fill: 'forwards'
        });

        const fadeInAnim = inElement.animate([
            { opacity: 0 },
            { opacity: 1 }
        ], {
            duration: prefersReducedMotion ? 0 : duration,
            easing: 'ease-in',
            fill: 'forwards'
        });

        const animId1 = Symbol('crossfadeOut');
        const animId2 = Symbol('crossfadeIn');
        animationsRef.current.set(animId1, fadeOutAnim);
        animationsRef.current.set(animId2, fadeInAnim);

        return Promise.all([fadeOutAnim.finished, fadeInAnim.finished]).then(() => {
            animationsRef.current.delete(animId1);
            animationsRef.current.delete(animId2);
            inElement.style.opacity = '';
        });
    }, [prefersReducedMotion]);

    /**
     * Main transition orchestrator
     * Runs the full transition sequence
     */
    const triggerTransition = useCallback(async ({
        sharedElementKey,       // Key of shared element to animate
        targetRect,             // Target position for shared element
        exitElementKey,         // Key of element to fade out
        enterElementKey,        // Key of element to fade in  
        crossfadeOutKey,        // Key of element to crossfade out (e.g., old header)
        crossfadeInKey,         // Key of element to crossfade in (e.g., new header)
        onSwap                  // Callback to perform DOM/state swap
    }) => {
        // Cancel any in-progress transition
        if (isTransitioning) {
            cancelAll();
        }

        setIsTransitioning(true);
        onStart();

        try {
            const sharedElement = sharedElementKey ? getElement(sharedElementKey) : null;
            const exitElement = exitElementKey ? getElement(exitElementKey) : null;
            const enterElement = enterElementKey ? getElement(enterElementKey) : null;
            const crossfadeOutElement = crossfadeOutKey ? getElement(crossfadeOutKey) : null;
            const crossfadeInElement = crossfadeInKey ? getElement(crossfadeInKey) : null;

            // Phase 1: Move shared element (if provided)
            const sharedPromise = sharedElement && targetRect
                ? animateTransform(sharedElement, measureElement(sharedElement), targetRect)
                : Promise.resolve();

            // Phase 2: Fade out exit element (parallel)
            const exitPromise = exitElement
                ? fadeOut(exitElement)
                : Promise.resolve();

            await Promise.all([sharedPromise, exitPromise]);

            // Phase 3: DOM/state swap
            if (onSwap) {
                await onSwap();
            }

            // Phase 4: Fade in enter element
            if (enterElement) {
                await fadeIn(enterElement);
            }

            // Phase 5: Crossfade (if provided)
            if (crossfadeOutElement && crossfadeInElement) {
                await crossfade(crossfadeOutElement, crossfadeInElement);
            }

            setIsTransitioning(false);
            onComplete();

        } catch (error) {
            console.error('Transition error:', error);
            setIsTransitioning(false);
        }
    }, [isTransitioning, cancelAll, onStart, onComplete, getElement, measureElement, animateTransform, fadeOut, fadeIn, crossfade]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            cancelAll();
        };
    }, [cancelAll]);

    return {
        // Registration
        registerElement,
        getElement,

        // Measurement
        measureElement,

        // Individual animations
        animateTransform,
        fadeOut,
        fadeIn,
        crossfade,

        // Orchestration
        triggerTransition,
        cancelAll,

        // State
        isTransitioning,
        prefersReducedMotion
    };
}

export default useSharedTransition;

// ============================================
// INTEGRATION NOTES
// ============================================
/*
Usage in a React component:

1. Import the hook and CSS tokens:
   import { useSharedTransition } from './useSharedTransition';
   import './shared-transition-tokens.css';

2. Initialize the hook:
   const { registerElement, triggerTransition, isTransitioning } = useSharedTransition({
     sharedKeys: ['activeIndicator'],
     onComplete: () => console.log('done')
   });

3. Register elements using ref callbacks:
   <div ref={registerElement('activeIndicator')} className="indicator" />
   <div ref={registerElement('content-home')} className="panel" />

4. Trigger transitions on navigation:
   const handleNavClick = (targetId) => {
     const targetIcon = document.querySelector(`[data-id="${targetId}"]`);
     const targetRect = targetIcon.getBoundingClientRect();
     
     triggerTransition({
       sharedElementKey: 'activeIndicator',
       targetRect,
       exitElementKey: `content-${currentPanel}`,
       enterElementKey: `content-${targetId}`,
       onSwap: () => setCurrentPanel(targetId)
     });
   };

5. The hook automatically:
   - Respects prefers-reduced-motion
   - Cancels and snaps on rapid clicks
   - Uses CSS variables for all timings
   - Cleans up animations on unmount
*/
