"""Check the site's analytic derivative rows against the reduction equations.

Run from any directory: python tools/verify_derivation.py
No laboratory data or diagnostic covariance substitutions are used.
"""
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from IDTIMS_UPbRPy import utils, constants


def complex_gradient(fn, x):
    gradient = np.empty(len(x))
    for i in range(len(x)):
        z = np.array(x, dtype=complex)
        z[i] += 1e-30j
        gradient[i] = fn(z).imag / 1e-30
    return gradient


def check():
    rng = np.random.default_rng(2007)
    for _ in range(32):
        # Coordinates: r,q,h,k,f,a,d,z,e,b,v,w,c,l,j,B.
        x = np.array([10,.001,.06,2,.001,.001,.0001,.08,.002,
                      18,.86,2.1,17,.9,37,1e-15])
        x *= rng.uniform(.85,1.15,len(x))
        T = 1e-12
        r,q,h,k,f,a,d,z,e,b,v,w,c,l,j,B = x
        C = T*(r*q*(1-f)-d)-B/b
        p = np.array([T*((1+f)-c*q*(1-f)),-c*T*r*(1-f),0,0,
                      T*r*(1+c*q),-T,c*T,0,0,-c*B/b**2,0,0,-C,0,0,c/b-1])
        qg = np.array([T*(h*(1+2*f)-c*l*q*(1-f)),-c*l*T*r*(1-f),T*r*(1+2*f),0,
                       T*r*(2*h+c*l*q),-T*z,c*l*T,-T*a,0,-c*l*B/b**2,-B,0,-l*C,-c*C,0,c*l/b-v])
        hg = np.array([-j*T*q*(1-f),-j*T*r*(1-f),0,T*(1+3*f),3*T*k+j*T*r*q,
                       0,j*T,0,-T,-j*B/b**2,0,-B,0,0,-C,j/b-w])
        def amounts(t):
            r,q,h,k,f,a,d,z,e,b,v,w,c,l,j,B=t
            C=T*(r*q*(1-f)-d)-B/b
            P=utils.calc_Pb206r(r,q,f,T,a,d,c,b,B)
            Q=utils.calc_Pb207r(r,h,q,f,T,a,z,d,l,c,b,v,B)
            H=utils.calc_Pb208r(k,f,T,e,w*B,j*C)
            return P,Q,H
        for i, analytic in enumerate([p,qg,hg]):
            np.testing.assert_allclose(analytic, complex_gradient(lambda t:amounts(t)[i],x),rtol=1e-11,atol=1e-28)
        # All four FU rows and the total U derivative, including FU dependence.
        alpha,beta = np.array([.003,1.])*rng.uniform(.85,1.15,2)
        eta=constants.common_U238_U235
        S=1e-12
        physical_u=1e-10
        true_f=.001
        m=(physical_u+alpha*S)/(physical_u/eta+S)/(1+3*true_f)
        n=beta*S/(physical_u/eta+S)/(1-2*true_f)
        eta=constants.common_U238_U235
        N=beta*(eta-m)+n*(alpha-eta); D=2*n*(alpha-eta)+3*beta*m
        fg=np.array([-beta/D-3*beta*N/D**2,(alpha-eta)/D-2*(alpha-eta)*N/D**2,
                     n/D-2*n*N/D**2,(eta-m)/D-3*m*N/D**2])
        fu=lambda t:utils.calc_FU(t[1],t[0],t[3],t[2],eta)
        np.testing.assert_allclose(fg,complex_gradient(fu,[m,n,alpha,beta]),rtol=1e-11)
        S,Z=1e-12,1e-16
        F=fu([m,n,alpha,beta]);L=1+3*F;K=1-m*L/eta;V=S*m*L-S*alpha-Z
        UF=3*S*m/K+3*m*V/(eta*K*K)
        ug=UF*np.r_[fg,0.]
        ug[0]+=S*L/K+V*L/(eta*K*K);ug[2]-=S/K;ug[4]=-1/K
        U=lambda t:utils.calc_U238s(t[0],fu(t),S,t[2],t[4],eta)
        np.testing.assert_allclose(ug,complex_gradient(U,[m,n,alpha,beta,Z]),rtol=1e-11,atol=1e-27)
        # Ratio covariance versus the redundant-ratio identities.
        P,Q,H=amounts(x);u=U([m,n,alpha,beta,Z])
        vv=np.array([P,Q,H,u])
        J=np.array([[1/u,0,0,-P/u**2],[0,eta/u,0,-eta*Q/u**2],
                    [-Q/P**2,1/P,0,0],[-u/P**2,0,0,1/P],[0,-u/Q**2,0,1/Q]])
        A=rng.normal(size=(4,4));cov=(A@A.T)*1e-32
        result=J@cov@J.T
        ratios=np.array([P/u,eta*Q/u,Q/P,u/P,u/Q])
        errors=np.sqrt(np.diag(result))/np.abs(ratios)
        for first,second,quotient in [(1,0,2),(3,2,4)]:
            inferred=(errors[first]**2+errors[second]**2-errors[quotient]**2)/(2*errors[first]*errors[second])
            direct=result[first,second]/np.sqrt(result[first,first]*result[second,second])
            np.testing.assert_allclose(inferred,direct,atol=1e-12)
    for age in [.001,.1,1,640,3000,4600]:
        a,b=constants.lambda_235*1e6,constants.lambda_238*1e6
        derivative=(a*np.exp(a*age)*np.expm1(b*age)-b*np.exp(b*age)*np.expm1(a*age))/(constants.common_U238_U235*np.expm1(b*age)**2)
        np.testing.assert_allclose(utils.calc_t76_uncertainty(age,1e-5),1e-5/abs(derivative),rtol=2e-6)
    print('PASS: 32 cases of Pb amount/FU/total-U derivatives and ratio correlation identities; 6 Pb–Pb inverse-derivative cases.')


if __name__ == '__main__':
    check()
