/**
 * FAA ATC HTML5 - Navigation JavaScript
 * Handles sidebar toggle, expand/collapse, session storage persistence,
 * navbar burger menu, and smooth scrolling for anchor links.
 */
!function() {
  'use strict';

  // === Sidebar Navigation ===
  var nav = document.querySelector('.navigation-container');
  var toggle = document.querySelector('.navigation-toggle');

  if (toggle && nav) {
    toggle.addEventListener('click', function(e) {
      if (toggle.classList.contains('is-active')) {
        closeNav(e);
        return;
      }
      document.documentElement.classList.add('is-clipped--nav');
      toggle.classList.add('is-active');
      nav.classList.add('is-active');
      window.addEventListener('click', closeNav);
      stopProp(e);
    });

    nav.addEventListener('click', stopProp);

    // Menu panel
    var menuPanel = nav.querySelector('[data-panel=menu]');
    if (menuPanel) {
      var navState;
      try {
        var stored = window.sessionStorage.getItem('nav-state');
        navState = stored && JSON.parse(stored);
        if (!navState || navState.__version__ !== '1') {
          navState = { __version__: '1' };
        }
      } catch (e) {
        navState = { __version__: '1' };
      }

      var component = nav.dataset.component || 'atc';
      var version = nav.dataset.version || 'BB';
      var stateKey = version + '@' + component;
      var pageState = navState[stateKey] || (navState[stateKey] = {});

      // Set up nav toggle buttons
      queryAll('.nav-toggle', menuPanel).forEach(function(btn) {
        var item = btn.parentElement;
        btn.addEventListener('click', function() {
          item.classList.toggle('is-active');
          pageState.expandedItems = getExpandedItems();
          saveState();
        });

        // Also toggle on nav-text click
        var textEl = btn.nextElementSibling;
        if (textEl && textEl.classList && textEl.classList.contains('nav-text')) {
          textEl.style.cursor = 'pointer';
          textEl.addEventListener('click', function() {
            item.classList.toggle('is-active');
            pageState.expandedItems = getExpandedItems();
            saveState();
          });
        }
      });

      // Assign data-id to each nav-item
      queryAll('.nav-item', menuPanel).forEach(function(item, idx) {
        item.setAttribute('data-id', 'menu-' + (item.dataset.depth || '0') + '-' + idx);
      });

      // Restore expanded items from session
      var expanded = pageState.expandedItems || (pageState.expandedItems = []);
      if (expanded.length) {
        var selector = expanded.map(function(id) {
          return '.nav-item[data-id="' + id + '"]';
        }).join(',');
        queryAll(selector, menuPanel).forEach(function(item) {
          item.classList.add('is-active');
        });
      }

      // Activate current page path
      var currentPage = menuPanel.querySelector('.is-current-page');
      if (currentPage) {
        var ids = activatePath(currentPage);
        ids.forEach(function(id) {
          if (expanded.indexOf(id) < 0) expanded.push(id);
        });
      }

      saveState();

      // Restore scroll position
      var savedScroll = pageState.scroll || 0;
      var currentLink = currentPage && currentPage.querySelector('.nav-link');
      restoreScroll(savedScroll, menuPanel, currentLink);

      // Save scroll position on scroll
      menuPanel.addEventListener('scroll', function() {
        pageState.scroll = Math.round(menuPanel.scrollTop);
        saveState();
      });
    }
  }

  function closeNav(e) {
    if (e.which === 3 || e.button === 2) return;
    document.documentElement.classList.remove('is-clipped--nav');
    if (toggle) toggle.classList.remove('is-active');
    if (nav) nav.classList.remove('is-active');
    window.removeEventListener('click', closeNav);
    stopProp(e);
  }

  function stopProp(e) {
    e.stopPropagation();
  }

  function getExpandedItems() {
    return queryAll('.is-active', menuPanel).map(function(el) {
      return el.dataset.id;
    }).filter(Boolean);
  }

  function saveState() {
    try {
      window.sessionStorage.setItem('nav-state', JSON.stringify(navState));
    } catch (e) {
      // sessionStorage may be unavailable
    }
  }

  function activatePath(item) {
    var ids = [item.dataset.id];
    var parent = item.parentNode;
    while (parent && !parent.classList.contains('nav-menu')) {
      if (parent.tagName === 'LI' && parent.classList.contains('nav-item')) {
        parent.classList.add('is-active', 'is-current-path');
        ids.push(parent.dataset.id);
      }
      parent = parent.parentNode;
    }
    item.classList.add('is-active');
    return ids;
  }

  function restoreScroll(savedScroll, container, currentLink) {
    if (!currentLink) {
      container.scrollTop = savedScroll;
      return;
    }
    var linkTop = currentLink.offsetTop;
    if (linkTop < savedScroll) {
      container.scrollTop = linkTop - 10;
    } else if (linkTop - container.offsetHeight + currentLink.offsetHeight > savedScroll) {
      container.scrollTop = linkTop - container.offsetHeight + currentLink.offsetHeight + 10;
    } else {
      container.scrollTop = savedScroll;
    }
  }

  function queryAll(selector, context) {
    return [].slice.call((context || document).querySelectorAll(selector));
  }

  // === Navbar Burger Menu ===
  document.addEventListener('DOMContentLoaded', function() {
    var burgers = [].slice.call(document.querySelectorAll('.navbar-burger'), 0);
    burgers.forEach(function(burger) {
      burger.addEventListener('click', function(e) {
        e.stopPropagation();
        burger.classList.toggle('is-active');
        var target = document.getElementById(burger.dataset.target);
        if (target) target.classList.toggle('is-active');
        document.documentElement.classList.toggle('is-clipped--navbar');
      });
    });
  });

  // === Smooth Scrolling for Anchor Links ===
  function getScrollOffset() {
    var header = document.querySelector('header.header');
    return header ? header.offsetHeight + 20 : 80;
  }

  function scrollToElement(targetId) {
    var target = document.getElementById(targetId);
    if (!target) return false;
    var offset = getScrollOffset();
    var targetPosition = target.getBoundingClientRect().top + window.pageYOffset - offset;
    window.scrollTo({ top: targetPosition, behavior: 'smooth' });
    target.style.transition = 'background-color 0.3s ease';
    target.style.backgroundColor = '#fff3cd';
    setTimeout(function() { target.style.backgroundColor = ''; }, 2000);
    return true;
  }

  if (window.location.hash) {
    window.addEventListener('load', function() {
      setTimeout(function() {
        var hash = window.location.hash.substring(1);
        if (hash) scrollToElement(hash);
      }, 150);
    });
  }

  window.addEventListener('hashchange', function() {
    var hash = window.location.hash.substring(1);
    if (hash) scrollToElement(hash);
  });

  document.addEventListener('click', function(e) {
    var el = e.target;
    if (el.tagName === 'A' && el.hash) {
      var hash = el.hash.substring(1);
      if (el.pathname === window.location.pathname || el.pathname === '' || el.pathname === '/') {
        e.preventDefault();
        if (scrollToElement(hash)) {
          history.pushState(null, null, '#' + hash);
        }
      }
    }
  });
}();
