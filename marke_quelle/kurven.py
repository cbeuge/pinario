"""Kurvenanpassung nach Schneider.

Der erste Versuch legte durch jeden Punkt des vereinfachten Umrisses eine
Catmull-Rom-Kurve. Das trifft die Vorlage, uebernimmt aber auch jede
Unebenheit des 92 Pixel hohen Originals: bei zwoelffacher Vergroesserung
beult die Punze des p sichtbar aus.

Hier wird stattdessen je Abschnitt zwischen zwei Ecken die kleinste Zahl
kubischer Bezier gesucht, die den Punktzug innerhalb einer Toleranz trifft
(Least Squares mit Newton-Reparametrisierung, Teilung nur wenn noetig).
Ergebnis: wenige lange Kurven statt vieler kurzer, und damit glatte
Buchstaben.
"""
import math


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _mul(a, s):
    return (a[0] * s, a[1] * s)


def _punkt(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _norm(a):
    laenge = math.hypot(a[0], a[1])
    return (0.0, 0.0) if laenge == 0 else (a[0] / laenge, a[1] / laenge)


def _bezier(steuer, t):
    u = 1 - t
    return (
        u ** 3 * steuer[0][0] + 3 * u * u * t * steuer[1][0]
        + 3 * u * t * t * steuer[2][0] + t ** 3 * steuer[3][0],
        u ** 3 * steuer[0][1] + 3 * u * u * t * steuer[1][1]
        + 3 * u * t * t * steuer[2][1] + t ** 3 * steuer[3][1],
    )


def _tangente(punkte, i, fenster=8):
    """Richtung an einer Stelle, gemittelt ueber die Nachbarschaft.

    Ein einzelner Nachbarpunkt liegt auf einer Treppenstufe und zeigt
    deshalb entweder waagerecht oder senkrecht, nie in die tatsaechliche
    Richtung der Kurve."""
    n = len(punkte)
    a = punkte[max(0, i - fenster)]
    b = punkte[min(n - 1, i + fenster)]
    return _norm(_sub(b, a))


def _parametrisieren(punkte):
    u = [0.0]
    for i in range(1, len(punkte)):
        u.append(u[-1] + math.hypot(*_sub(punkte[i], punkte[i - 1])))
    gesamt = u[-1]
    if gesamt == 0:
        return [i / max(1, len(punkte) - 1) for i in range(len(punkte))]
    return [v / gesamt for v in u]


def _bezier_bilden(punkte, u, t1, t2):
    """Die beiden inneren Kontrollpunkte per kleinster Fehlerquadrate."""
    n = len(punkte)
    a = []
    for i in range(n):
        t = u[i]
        a.append((_mul(t1, 3 * (1 - t) ** 2 * t), _mul(t2, 3 * (1 - t) * t * t)))

    c00 = c01 = c11 = x0 = x1 = 0.0
    for i in range(n):
        c00 += _punkt(a[i][0], a[i][0])
        c01 += _punkt(a[i][0], a[i][1])
        c11 += _punkt(a[i][1], a[i][1])
        t = u[i]
        auf_linie = (
            _mul(punkte[0], (1 - t) ** 3 + 3 * (1 - t) ** 2 * t)[0]
            + _mul(punkte[-1], 3 * (1 - t) * t * t + t ** 3)[0],
            _mul(punkte[0], (1 - t) ** 3 + 3 * (1 - t) ** 2 * t)[1]
            + _mul(punkte[-1], 3 * (1 - t) * t * t + t ** 3)[1],
        )
        rest = _sub(punkte[i], auf_linie)
        x0 += _punkt(a[i][0], rest)
        x1 += _punkt(a[i][1], rest)

    nenner = c00 * c11 - c01 * c01
    strecke = math.hypot(*_sub(punkte[-1], punkte[0]))
    if abs(nenner) < 1e-12:
        alpha1 = alpha2 = strecke / 3
    else:
        alpha1 = (x0 * c11 - x1 * c01) / nenner
        alpha2 = (c00 * x1 - c01 * x0) / nenner

    # Ausreisser abfangen: negative oder riesige Laengen entstehen, wenn der
    # Punktzug fast gerade ist. Dann ist das Drittel die richtige Antwort.
    if alpha1 < 1e-6 or alpha2 < 1e-6 or alpha1 > strecke * 2 or alpha2 > strecke * 2:
        alpha1 = alpha2 = strecke / 3

    return [punkte[0], _add(punkte[0], _mul(t1, alpha1)),
            _add(punkte[-1], _mul(t2, alpha2)), punkte[-1]]


def _fehler(punkte, u, steuer):
    weit, idx = 0.0, len(punkte) // 2
    for i in range(len(punkte)):
        d = math.hypot(*_sub(_bezier(steuer, u[i]), punkte[i]))
        if d > weit:
            weit, idx = d, i
    return weit, idx


def _nachziehen(punkte, u, steuer):
    """Newton-Raphson: jeden Punkt auf den Parameter schieben, an dem die
    Kurve ihm am naechsten kommt."""
    neu = []
    for i, p in enumerate(punkte):
        t = u[i]
        q = _bezier(steuer, t)
        d1 = [_mul(_sub(steuer[k + 1], steuer[k]), 3) for k in range(3)]
        d2 = [_mul(_sub(d1[k + 1], d1[k]), 2) for k in range(2)]
        qs = (
            (1 - t) ** 2 * d1[0][0] + 2 * (1 - t) * t * d1[1][0] + t * t * d1[2][0],
            (1 - t) ** 2 * d1[0][1] + 2 * (1 - t) * t * d1[1][1] + t * t * d1[2][1],
        )
        qss = ((1 - t) * d2[0][0] + t * d2[1][0], (1 - t) * d2[0][1] + t * d2[1][1])
        zaehler = _punkt(_sub(q, p), qs)
        nenner = _punkt(qs, qs) + _punkt(_sub(q, p), qss)
        neu.append(t if abs(nenner) < 1e-12 else min(1.0, max(0.0, t - zaehler / nenner)))
    return neu


def anpassen(punkte, t1, t2, toleranz, tiefe=0):
    """Liefert eine Liste kubischer Bezier, die den Punktzug abdecken."""
    if len(punkte) < 2:
        return []
    if len(punkte) == 2:
        strecke = math.hypot(*_sub(punkte[1], punkte[0])) / 3
        return [[punkte[0], _add(punkte[0], _mul(t1, strecke)),
                 _add(punkte[1], _mul(t2, strecke)), punkte[1]]]

    u = _parametrisieren(punkte)
    steuer = _bezier_bilden(punkte, u, t1, t2)
    weit, idx = _fehler(punkte, u, steuer)
    if weit < toleranz:
        return [steuer]

    if weit < toleranz * 16 and tiefe < 24:
        for _ in range(12):
            u = _nachziehen(punkte, u, steuer)
            steuer = _bezier_bilden(punkte, u, t1, t2)
            weit, idx = _fehler(punkte, u, steuer)
            if weit < toleranz:
                return [steuer]

    if tiefe > 24 or idx <= 0 or idx >= len(punkte) - 1:
        return [steuer]

    mitte = _tangente(punkte, idx)
    links = anpassen(punkte[:idx + 1], t1, _mul(mitte, -1), toleranz, tiefe + 1)
    rechts = anpassen(punkte[idx:], mitte, t2, toleranz, tiefe + 1)
    return links + rechts
