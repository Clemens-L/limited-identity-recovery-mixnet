import hashlib
import logging

import elgamal
from typing import List, Dict, Iterator, Union, Tuple
from gmpy2 import mpz
from integer import SchnorrGroup, random_integer

logger = logging.getLogger(__name__)


def hashfunc(G_q: SchnorrGroup, values: List[Union[mpz, int]]) -> mpz:
    h = hashlib.sha256()
    for v in values:
        if isinstance(v, int):
            v = mpz(v)
        h.update(v.digits().encode())
    # reduce it mod q, as it is only used in exponents (and in r, which is also reduced mod q)
    c = mpz(int.from_bytes(bytes=h.digest(), byteorder='little')) % G_q.order()
    return c


def hashfunc_bits(values: List[mpz]) -> List[int]:
    def _bits_from_bytes(array: bytes) -> Iterator[int]:
        for b in array:
            for i in range(8):
                yield (b >> i) & 1

    h = hashlib.sha256()
    for v in values:
        h.update(v.digits().encode())
    c = h.digest()

    return list(_bits_from_bytes(c))


DLEQProofTranscript = Tuple[mpz, mpz, mpz]


def proof_dleq(G_q: SchnorrGroup, g_1: mpz, h_1: mpz, g_2: mpz, h_2: mpz, alpha: mpz) -> DLEQProofTranscript:
    """
    Performs a simple equality proof for the two discrete logarithms of two public elements. This is known
    as the Chaum Pedersen protocol.
    :param G_q: Group of prime order
    :param g_1: Base of the first logarithm
    :param h_1: First public element
    :param g_2: Base of the second logarithm
    :param h_2: Second public element
    :param alpha: The secret logarithm of both elements
    :return: A proof transcript (t_1, t_2, res)
    """
    w = random_integer(0, G_q.order())

    t_1 = G_q.powmod(g_1, w)
    t_2 = G_q.powmod(g_2, w)

    c = hashfunc(G_q, [h_1, h_2, t_1, t_2])

    res = (w - alpha * c) % G_q.q

    return t_1, t_2, res


def verify_dleq(G_q: SchnorrGroup, proof: DLEQProofTranscript, g_1: mpz, h_1: mpz, g_2: mpz, h_2: mpz) -> bool:
    """
    Verifies a DLEQ proof generated by the Chaum Pedersen protocol.
    :param G_q: Group of prime order
    :param proof: Proof transcript (t_1, t_2, res) generated by the prover
    :param g_1: Base of the first logarithm
    :param h_1: First public element
    :param g_2: Base of the second logarithm
    :param h_2: Second public element
    :return: True, iff the verification is successful
    """
    t_1, t_2, res = proof
    c = hashfunc(G_q, [h_1, h_2, t_1, t_2])

    b_1 = (t_1 == G_q.powmod(g_1, res) * G_q.powmod(h_1, c) % G_q.p)
    b_2 = (t_2 == G_q.powmod(g_2, res) * G_q.powmod(h_2, c) % G_q.p)

    return b_1 and b_2


def proof_correct_decryption(key: elgamal.ElGamalKeypair, c: elgamal.ElGamalCiphertext, m: mpz,
                             r: mpz) -> DLEQProofTranscript:
    """
    Given a public elgamal key, a ciphertext c (along with its random value r) and a publicly known message m,
    this generates a proof that c can be decrypted to m. (Proof of correct decryption)
    :param key: The public ElGamal key used
    :param c: The publicly known ciphertext
    :param m: The publicly known message
    :param r: The secret random value used to encrypt c
    :return: A proof transcript (t_1, t_2, res)
    """
    return proof_dleq(c.G_q, key.g, c.a, key.y, c.b * c.G_q.powmod(m, -1) % c.G_q.p, r)


def verify_correct_decryption(proof: DLEQProofTranscript, key: elgamal.ElGamalKeypair, c: elgamal.ElGamalCiphertext,
                              m: mpz) -> bool:
    """
    Verifies a proof of correct decryption.
    :param proof: Proof transcript (t_1, t_2, res) generated by the prover.
    :param key: The public ElGamal key used
    :param c: The publicly known ciphertext
    :param m: The publicly known message
    :return: True, iff the verification is successful
    """
    return verify_dleq(c.G_q, proof, key.g, c.a, key.y, c.b * c.G_q.powmod(m, -1) % c.G_q.p)


def proof_plaintext_equality(key: elgamal.ElGamalKeypair, c: elgamal.ElGamalCiphertext, r: mpz,
                             c_prime: elgamal.ElGamalCiphertext, r_prime: mpz) -> DLEQProofTranscript:
    """
    Proves that a ciphertext c is plaintext equal to a ciphertext c_prime
    :param key: The public ElGamal key used to encrypt all ciphertexts
    :param c: The ciphertext c
    :param r: The random value used in the encryption of c
    :param c_prime: The ciphertext c_prime
    :param r_prime: The random value used in the encryption of c_prime
    :return: A proof transcript (t_1, t_2, res)
    """
    r_hat = (r_prime - r) % key.G_q.order()
    a_hat = c_prime.a * c.G_q.powmod(c.a, -1) % c.G_q.p
    b_hat = c_prime.b * c.G_q.powmod(c.b, -1) % c.G_q.p
    return proof_dleq(c.G_q, key.g, a_hat, key.y, b_hat, r_hat)


def verify_plaintext_equality(proof: DLEQProofTranscript, key: elgamal.ElGamalKeypair,
                              c: elgamal.ElGamalCiphertext, c_prime: elgamal.ElGamalCiphertext) -> bool:
    """
    Verifies a proof of plaintext equality
    :param proof: Proof transcript (t_1, t_2, res) generated by the prover.
    :param key: The public ElGamal key used
    :param c: The publicly known ciphertext c
    :param c_prime: The publicly known ciphertext c_prime
    :return: True, iff the verification is successful
    """
    a_hat = c_prime.a * c.G_q.powmod(c.a, -1) % c.G_q.p
    b_hat = c_prime.b * c.G_q.powmod(c.b, -1) % c.G_q.p
    return verify_dleq(c.G_q, proof, key.g, a_hat, key.y, b_hat)


PlaintextEqualityORProof = Tuple[List[Tuple[mpz, mpz]], List[mpz], List[mpz]]


def proof_plaintext_equality_or(key: elgamal.ElGamalKeypair, c: elgamal.ElGamalCiphertext, r: mpz,
                                c_prime: List[elgamal.ElGamalCiphertext], j: int, r_j: mpz) -> PlaintextEqualityORProof:
    """
    Proves that a ciphertext c is plaintext equal to at least one of ciphertext of the list c_prime.
    The ciphertext that is actually plaintext equal to c must be indicated by the index j.
    :param key: The public ElGamal key used to encrypt all ciphertexts
    :param c: The ciphertext c
    :param r: The random value used in the encryption of c
    :param c_prime: A list of ciphertexts
    :param j: The index of the correct, plaintext equal ciphertext
    :param r_j: The random value used in the encryption of c_prime[j]
    :return: A proof transcript (t, res, challenges)
    """
    G_q = key.G_q

    # initialize list of commitments
    t = [(None, None) for _ in c_prime]
    res = [None for _ in c_prime]
    challenges = [None for _ in c_prime]

    # j is the index of the correct ciphertext
    # prepare "real" commitment values for the actual proof
    w_j = random_integer(0, G_q.order())
    t[j] = G_q.powmod(key.g, w_j), G_q.powmod(key.y, w_j)

    a_inv = G_q.powmod(c.a, -1)
    b_inv = G_q.powmod(c.b, -1)

    for i in range(len(c_prime)):
        if i == j:
            continue
        # pick random values for challenge and response
        res[i] = random_integer(0, G_q.order())
        challenges[i] = random_integer(0, G_q.order())
        # forge proof by computing matching commitment values
        t1 = G_q.powmod(key.g, res[i]) * G_q.powmod(c_prime[i].a * a_inv, challenges[i]) % G_q.p
        t2 = G_q.powmod(key.y, res[i]) * G_q.powmod(c_prime[i].b * b_inv, challenges[i]) % G_q.p
        t[i] = t1, t2

    # compute hash function to receive "master challenge"
    challenge = hashfunc(
        G_q,
        [c.a] + [c.a for c in c_prime] + [c.b] + [c.b for c in c_prime]
        + [ti1 for ti1, _ in t] + [ti2 for _, ti2 in t]
    )

    # we define that the "subchallenges" must add up to the "master challenge"
    # compute the challenge for the actual subproof (which we cannot choose freely now)
    challenges[j] = (challenge - sum(challenges[i] for i in range(len(challenges)) if i != j)) % G_q.p
    # compute the response for the actual proof
    res[j] = (w_j - (r_j - r) * challenges[j]) % G_q.order()

    return t, res, challenges


def verify_plaintext_equality_or(proof: PlaintextEqualityORProof, key: elgamal.ElGamalKeypair,
                                 c: elgamal.ElGamalCiphertext,
                                 c_prime: List[elgamal.ElGamalCiphertext]) -> bool:
    """
    Verifies the plaintext-equality-or-proof.
    :param proof: Proof transcript (t, res, challenges) generated by the prover
    :param key: The public ElGamal key used to encrypt the ciphertexts
    :param c: The ciphertext c
    :param c_prime: The list of ciphertext alternatives, of which one must be plaintext equal to c
    :return: True, iff the verification is successful
    """
    G_q = key.G_q
    t, res, challenges = proof
    assert len(challenges) == len(res) == len(t) == len(c_prime)
    # compute hash function to receive "master challenge"
    challenge = hashfunc(
        G_q,
        [c.a] + [c.a for c in c_prime] + [c.b] + [c.b for c in c_prime]
        + [ti1 for ti1, _ in t] + [ti2 for _, ti2 in t]
    )
    # check that the sum of all individual challenges equals the hash value
    b_sum_of_challenges = challenge == (sum(challenges) % G_q.p)
    logger.debug(f"b_sum_of_challenges = {b_sum_of_challenges}")

    a_inv = G_q.powmod(c.a, -1)
    b_inv = G_q.powmod(c.b, -1)

    b1 = []
    b2 = []
    for ti1ti2, res_i, challenge_i, c_prime_i in zip(t, res, challenges, c_prime):
        ti1, ti2 = ti1ti2
        b1.append(ti1 == (G_q.powmod(key.g, res_i) * G_q.powmod(c_prime_i.a * a_inv, challenge_i) % G_q.p))
        b2.append(ti2 == (G_q.powmod(key.y, res_i) * G_q.powmod(c_prime_i.b * b_inv, challenge_i) % G_q.p))
    return b_sum_of_challenges and all(b1) and all(b2)


PlaintextDLogPoK = Tuple[mpz, mpz, mpz, mpz]


def proof_plaintext_dlog(key: elgamal.ElGamalKeypair, c: elgamal.ElGamalCiphertext, h: mpz, x: mpz,
                         r: mpz) -> PlaintextDLogPoK:
    """
    Proves that the plaintext of c is an element of which we know the discrete logarithm x to the base h.
    :param key: The public ElGamal key used to encrypt c.
    :param c: The ciphertext c.
    :param h: The base h of the encrypted element.
    :param x: The exponent x of the encrypted element.
    :param r: The random value used during the encryption.
    :return: A proof transcript (t_1, t_2, res1, res2)
    """
    G_q = key.G_q
    a, b = c.a, c.b
    g = key.g
    y = key.y

    w_1 = random_integer(0, G_q.order())
    w_2 = random_integer(0, G_q.order())

    t_1 = G_q.powmod(h, w_1) * G_q.powmod(y, w_2) % G_q.p
    t_2 = G_q.powmod(g, w_2)

    challenge = hashfunc(G_q, [g, h, y, t_1, t_2, a, b])

    res1 = (w_1 + challenge * x) % G_q.order()
    res2 = (w_2 + challenge * r) % G_q.order()

    return t_1, t_2, res1, res2


def verify_plaintext_dlog(proof: PlaintextDLogPoK, key: elgamal.ElGamalKeypair, c: elgamal.ElGamalCiphertext,
                          h: mpz) -> bool:
    """
    Verifies the proof of knowledge of the discrete logarithm of an encrypted element.
    :param proof: The proof transcript (t_1, t_2, res1, res2) given by the prover.
    :param key: The public ElGamal key used to encrypt c.
    :param c: The ciphertext c.
    :param h: The base h of the discrete logarithm of the encrypted element.
    :return: True, iff the verification is successful.
    """
    G_q = key.G_q
    a, b = c.a, c.b
    g = key.g
    y = key.y

    t_1, t_2, res1, res2 = proof

    challenge = hashfunc(G_q, [g, h, y, t_1, t_2, a, b])

    b1 = (G_q.powmod(h, res1) * G_q.powmod(y, res2) % G_q.p) == (t_1 * G_q.powmod(b, challenge) % G_q.p)
    b2 = G_q.powmod(g, res2) == (t_2 * G_q.powmod(a, challenge) % G_q.p)

    return b1 and b2


# (c, r)
DLEqualDoubleDLProof = Tuple[List[mpz], List[mpz]]


def proof_dl_equal_ddl(G_q: SchnorrGroup, G_r: SchnorrGroup, g: mpz, h: mpz, y: mpz, A: mpz, B: mpz,
                       x: mpz) -> DLEqualDoubleDLProof:
    """
    Proves that the discrete logarithm of a public element A to the base h equals
    the double discrete logarithm of a public element B to the bases g and y.
    (i.e., that we know x s.t. A = h^x and B = g^(y^x))
    :param G_q: Group of order q, modulo p = 2*q + 1
    :param G_r: Group of order r, modulo q
    :param g: Generator of G_q
    :param h: Generator of G_r
    :param y: Generator of G_r
    :param A: Public element in G_q
    :param B: Public element in G_r
    :param x: Secret exponent
    :return: A proof transcript (c, r)
    """
    assert G_q.p == G_r.p * 2 + 1

    assert G_q.is_element(g)
    assert G_q.is_element(B)

    assert G_r.is_element(h)
    assert G_r.is_element(y)
    assert G_r.is_element(A)

    bits = 256

    w = []
    t_g = []
    t_h = []
    for i in range(bits):
        w_i = random_integer(0, G_r.order())
        t_gi = G_q.powmod(g, G_r.powmod(y, w_i))
        t_hi = G_r.powmod(h, w_i)

        w.append(w_i)
        t_g.append(t_gi)
        t_h.append(t_hi)

    c = hashfunc_bits([g, h, y, A, B] + t_g + t_h)

    r = [
        (w_i - c_i * x) % G_r.order()
        for c_i, w_i in zip(c, w)
    ]

    return c, r


def verify_dl_equal_ddl(proof: DLEqualDoubleDLProof, G_q: SchnorrGroup, G_r: SchnorrGroup, g: mpz, h: mpz, y: mpz,
                        A: mpz, B: mpz) -> bool:
    """
    Verifies the "discrete logarithm equals double discrete logarithm" proof.
    :param proof: Proof transcript (c, r) generated by the prover
    :param G_q: Group of order q, modulo p = 2*q + 1
    :param G_r: Group of order r, modulo q
    :param g: Generator of G_q
    :param h: Generator of G_r
    :param y: Generator of G_r
    :param A: Public element in G_q
    :param B: Public element in G_r
    :return: True, iff the verification is successful.
    """
    assert G_q.p == G_r.p * 2 + 1

    assert G_q.is_element(g)
    assert G_q.is_element(B)

    assert G_r.is_element(h)
    assert G_r.is_element(y)
    assert G_r.is_element(A)

    c, r = proof

    t_g = []
    t_h = []

    for r_i, c_i in zip(r, c):
        t_gi = (G_q.powmod(B if c_i else g, G_r.powmod(y, r_i)))
        t_hi = (G_r.powmod(h, r_i) * G_r.powmod(A, c_i) % G_r.p)
        t_g.append(t_gi)
        t_h.append(t_hi)

    c_new = hashfunc_bits([g, h, y, A, B] + t_g + t_h)

    return c == c_new
