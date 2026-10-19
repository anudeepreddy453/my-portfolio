(function () {
  var toggle = document.getElementById("nav-toggle");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    function setExpanded() {
      toggle.setAttribute("aria-expanded", toggle.checked ? "true" : "false");
    }

    toggle.setAttribute("aria-expanded", "false");
    toggle.addEventListener("change", setExpanded);

    nav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        if (toggle.checked) {
          toggle.checked = false;
          setExpanded();
        }
      });
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && toggle.checked) {
        toggle.checked = false;
        setExpanded();
        toggle.focus();
      }
    });
  }

  // Soft header contrast when leaving the photographic hero
  var header = document.querySelector(".site-header");
  var hero = document.querySelector(".hero");
  if (header && hero && "IntersectionObserver" in window) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          header.classList.toggle("is-scrolled", !entry.isIntersecting);
        });
      },
      { rootMargin: "-12% 0px 0px 0px", threshold: 0 }
    );
    observer.observe(hero);
  }
})();
